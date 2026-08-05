#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    from .motherboard_kb import load_catalog, model_key, save_catalog
    from .reference_regions import normalize_polygon
    from .socket_geometry import rectangle_candidates
except ImportError:
    from motherboard_kb import load_catalog, model_key, save_catalog
    from reference_regions import normalize_polygon
    from socket_geometry import rectangle_candidates


def largest_board_rect(image: np.ndarray) -> tuple[int, int, int, int]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    edges = cv2.Canny(blurred, 35, 110)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = gray.shape
    minimum_area = width * height * 0.20
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < minimum_area:
            continue
        fill = cv2.contourArea(contour) / max(1.0, float(area))
        candidates.append((area * max(0.25, fill), (x, y, x + w, y + h)))
    if candidates:
        return max(candidates, key=lambda row: row[0])[1]
    return (0, 0, width, height)


def line_segments(image: np.ndarray, board: tuple[int, int, int, int]) -> list[dict[str, Any]]:
    x1, y1, x2, y2 = board
    roi = image[y1:y2, x1:x2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 45, 135)
    minimum = max(30, int(min(gray.shape) * 0.08))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=45, minLineLength=minimum, maxLineGap=18)
    rows = []
    if lines is None:
        return rows
    for raw in lines:
        line = np.asarray(raw).reshape(-1)
        if line.size != 4:
            continue
        ax, ay, bx, by = [int(value) for value in line]
        dx, dy = bx - ax, by - ay
        length = float((dx * dx + dy * dy) ** 0.5)
        orientation = 'horizontal' if abs(dx) >= abs(dy) else 'vertical'
        rows.append({
            'x1': ax + x1, 'y1': ay + y1, 'x2': bx + x1, 'y2': by + y1,
            'length': round(length, 2), 'orientation': orientation,
            'center_x': round((ax + bx) / 2 + x1, 2), 'center_y': round((ay + by) / 2 + y1, 2),
        })
    return rows


def cluster_parallel(lines: list[dict[str, Any]], orientation: str, axis_tolerance: float, min_count: int = 2) -> list[dict[str, Any]]:
    selected = [line for line in lines if line['orientation'] == orientation]
    key = 'center_x' if orientation == 'vertical' else 'center_y'
    selected.sort(key=lambda row: row[key])
    clusters: list[list[dict[str, Any]]] = []
    for line in selected:
        placed = False
        for cluster in clusters:
            center = sum(row[key] for row in cluster) / len(cluster)
            if abs(line[key] - center) <= axis_tolerance:
                cluster.append(line)
                placed = True
                break
        if not placed:
            clusters.append([line])
    output = []
    for cluster in clusters:
        if len(cluster) < min_count:
            continue
        output.append({
            'count': len(cluster),
            'axis_center': round(sum(row[key] for row in cluster) / len(cluster), 2),
            'mean_length': round(sum(row['length'] for row in cluster) / len(cluster), 2),
            'lines': cluster,
        })
    return output


def detect_slot_banks(image: np.ndarray, board: tuple[int, int, int, int]) -> dict[str, Any]:
    x1, y1, x2, y2 = board
    width, height = x2 - x1, y2 - y1
    lines = line_segments(image, board)
    vertical = cluster_parallel(lines, 'vertical', max(8.0, width * 0.018), 2)
    horizontal = cluster_parallel(lines, 'horizontal', max(8.0, height * 0.022), 2)
    dimm_candidates = []
    for cluster in vertical:
        normalized_x = (cluster['axis_center'] - x1) / max(1.0, width)
        normalized_length = cluster['mean_length'] / max(1.0, height)
        if normalized_x >= 0.45 and normalized_length >= 0.18:
            dimm_candidates.append(cluster)
    pcie_candidates = []
    for cluster in horizontal:
        normalized_y = (cluster['axis_center'] - y1) / max(1.0, height)
        normalized_length = cluster['mean_length'] / max(1.0, width)
        if normalized_y >= 0.35 and normalized_length >= 0.18:
            pcie_candidates.append(cluster)
    dimm = max(dimm_candidates, key=lambda row: (row['count'], row['mean_length']), default=None)
    pcie = max(pcie_candidates, key=lambda row: (row['count'], row['mean_length']), default=None)
    return {'lines': lines, 'dimm_bank': dimm, 'pcie_bank': pcie}


def infer_cpu_search_region(board: tuple[int, int, int, int], slots: dict[str, Any], port_buffer_ratio: float = 0.065) -> list[list[float]]:
    x1, y1, x2, y2 = board
    width, height = x2 - x1, y2 - y1
    io_inner = x1 + width * port_buffer_ratio
    top_inner = y1 + height * 0.05
    dimm_x = slots.get('dimm_bank', {}).get('axis_center') if slots.get('dimm_bank') else x1 + width * 0.76
    pcie_y = slots.get('pcie_bank', {}).get('axis_center') if slots.get('pcie_bank') else y1 + height * 0.58
    left = max(io_inner, x1 + width * 0.12)
    right = min(float(dimm_x) - width * 0.035, x1 + width * 0.72)
    top = top_inner
    bottom = min(float(pcie_y) - height * 0.035, y1 + height * 0.58)
    if right <= left:
        right = x1 + width * 0.68
    if bottom <= top:
        bottom = y1 + height * 0.52
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


def crop_polygon(image: np.ndarray, polygon: list[list[float]]) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
    return image[y1:y2, x1:x2], (x1, y1, x2, y2)


def select_socket_candidate(image: np.ndarray, cpu_region: list[list[float]], geometry_config: dict[str, Any]) -> dict[str, Any] | None:
    crop, bounds = crop_polygon(image, cpu_region)
    if crop.size == 0:
        return None
    local_config = dict(geometry_config)
    local_config['minimum_area_ratio'] = float(local_config.get('reference_minimum_area_ratio', 0.015))
    local_config['maximum_area_ratio'] = float(local_config.get('reference_maximum_area_ratio', 0.45))
    candidates = rectangle_candidates(crop, local_config)
    if not candidates:
        return None
    best = max(candidates, key=lambda row: row['score'])
    x1, y1, _, _ = bounds
    global_box = [best['box'][0] + x1, best['box'][1] + y1, best['box'][2] + x1, best['box'][3] + y1]
    return {**best, 'box': global_box}


def analyze_reference(image_path: Path, geometry_config: dict[str, Any], artifact_path: Path | None = None) -> dict[str, Any]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f'cannot decode image: {image_path}')
    board = largest_board_rect(image)
    slots = detect_slot_banks(image, board)
    cpu_region = infer_cpu_search_region(board, slots, float(geometry_config.get('port_buffer_ratio', 0.065)))
    socket = select_socket_candidate(image, cpu_region, geometry_config)
    if artifact_path:
        overlay = image.copy()
        bx1, by1, bx2, by2 = board
        cv2.rectangle(overlay, (bx1, by1), (bx2, by2), (255, 0, 0), 4)
        points = np.asarray(cpu_region, dtype=np.int32)
        cv2.polylines(overlay, [points], True, (0, 255, 255), 4)
        if slots.get('dimm_bank'):
            x = int(slots['dimm_bank']['axis_center'])
            cv2.line(overlay, (x, by1), (x, by2), (0, 255, 0), 4)
        if slots.get('pcie_bank'):
            y = int(slots['pcie_bank']['axis_center'])
            cv2.line(overlay, (bx1, y), (bx2, y), (0, 165, 255), 4)
        if socket:
            x1, y1, x2, y2 = socket['box']
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), 6)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(artifact_path), overlay)
    width, height = image.shape[1], image.shape[0]
    return {
        'image': str(image_path),
        'image_size': [width, height],
        'board_box': list(board),
        'slot_anchors': {'dimm_bank': slots.get('dimm_bank'), 'pcie_bank': slots.get('pcie_bank')},
        'cpu_search_region': cpu_region,
        'socket_candidate': socket,
        'artifact': str(artifact_path) if artifact_path else None,
    }


def write_layout_to_catalog(catalog_path: Path, model: str, reference_id: str, result: dict[str, Any]) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    key = model_key(model)
    board = catalog.get('boards', {}).get(key)
    if board is None:
        raise KeyError(f'board not found: {model}')
    width, height = result['image_size']
    board['layout'] = {
        'reference_id': reference_id,
        'board_box_normalized': normalize_polygon([
            [result['board_box'][0], result['board_box'][1]],
            [result['board_box'][2], result['board_box'][1]],
            [result['board_box'][2], result['board_box'][3]],
            [result['board_box'][0], result['board_box'][3]],
        ], width, height),
        'cpu_search_region_normalized': normalize_polygon(result['cpu_search_region'], width, height),
        'slot_anchors': result['slot_anchors'],
    }
    if result.get('socket_candidate'):
        x1, y1, x2, y2 = result['socket_candidate']['box']
        board.setdefault('regions', {})['cpu_socket'] = {
            'name': 'cpu_socket',
            'polygon_normalized': normalize_polygon([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], width, height),
            'reference_size': [width, height],
            'reference_id': reference_id,
            'derived_by': 'reference_layout_v1',
            'geometry_score': result['socket_candidate']['score'],
        }
    save_catalog(catalog_path, catalog)
    return board


def main() -> int:
    parser = argparse.ArgumentParser(description='Infer board, DIMM, PCIe, CPU search, and socket regions from a clean motherboard reference image')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--geometry-config', type=Path, default=Path('config/socket_geometry.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--artifact', type=Path)
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--model')
    parser.add_argument('--reference-id')
    args = parser.parse_args()
    config = json.loads(args.geometry_config.read_text(encoding='utf-8'))
    result = analyze_reference(args.image, config, args.artifact)
    if args.catalog or args.model or args.reference_id:
        if not (args.catalog and args.model and args.reference_id):
            raise ValueError('--catalog, --model, and --reference-id must be provided together')
        write_layout_to_catalog(args.catalog, args.model, args.reference_id, result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'socket_found': result['socket_candidate'] is not None, 'score': None if not result['socket_candidate'] else result['socket_candidate']['score']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
