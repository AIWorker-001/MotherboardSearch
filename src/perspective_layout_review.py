#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

COLORS = {
    'board': (255, 0, 0),
    'pcie_slots': (0, 255, 0),
    'dimm_slots': (0, 255, 255),
    'io_rectangle': (0, 165, 255),
    'cpu_search_region': (255, 0, 255),
    'cpu_socket': (0, 0, 255),
    'rear_cpu_bracket': (42, 42, 165),
}

LABELS = {
    'pcie_slots': 'PCI-E',
    'dimm_slots': 'DRAM',
    'io_rectangle': 'REAR I/O',
    'cpu_search_region': 'CPU SEARCH',
    'cpu_socket': 'EXPECTED SOCKET',
    'rear_cpu_bracket': 'REAR BRACKET',
}


def order_corners(points: list[list[float]]) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float32)
    if pts.shape != (4, 2):
        raise ValueError('board_corners must contain exactly four [x,y] points')
    sums = pts.sum(axis=1)
    differences = np.diff(pts, axis=1).reshape(-1)
    return np.asarray([
        pts[np.argmin(sums)],
        pts[np.argmin(differences)],
        pts[np.argmax(sums)],
        pts[np.argmax(differences)],
    ], dtype=np.float32)


def canonical_size(annotation: dict[str, Any]) -> tuple[int, int]:
    width, height = annotation.get('canonical_size', [1200, 1000])
    return int(width), int(height)


def homographies(annotation: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    source = order_corners(annotation['board_corners'])
    width, height = canonical_size(annotation)
    destination = np.asarray([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    forward = cv2.getPerspectiveTransform(source, destination)
    inverse = cv2.getPerspectiveTransform(destination, source)
    return forward, inverse


def project_polygon(points: list[list[float]], matrix: np.ndarray) -> list[list[int]]:
    polygon = np.asarray(points, dtype=np.float32).reshape(1, -1, 2)
    projected = cv2.perspectiveTransform(polygon, matrix).reshape(-1, 2)
    return np.rint(projected).astype(np.int32).tolist()


def normalized_to_pixels(points: list[list[float]], width: int, height: int) -> list[list[float]]:
    return [[float(x) * width, float(y) * height] for x, y in points]


def draw_polygon(image: np.ndarray, points: list[list[float]], color: tuple[int, int, int], label: str, thickness: int = 4, dashed: bool = False) -> None:
    pts = np.asarray(points, dtype=np.int32)
    if dashed:
        for index in range(len(pts)):
            start = pts[index]
            end = pts[(index + 1) % len(pts)]
            length = float(np.linalg.norm(end - start))
            segments = max(1, int(length / 18))
            for segment in range(0, segments, 2):
                a = segment / segments
                b = min(1.0, (segment + 1) / segments)
                p1 = np.rint(start + (end - start) * a).astype(int)
                p2 = np.rint(start + (end - start) * b).astype(int)
                cv2.line(image, tuple(p1), tuple(p2), color, thickness, cv2.LINE_AA)
    else:
        cv2.polylines(image, [pts], True, color, thickness, cv2.LINE_AA)
    x, y = pts[0]
    cv2.putText(image, label, (int(x) + 6, max(22, int(y) - 7)), cv2.FONT_HERSHEY_SIMPLEX, .62, color, 2, cv2.LINE_AA)


def render(image_path: Path, annotation_path: Path, normalized_output: Path, original_output: Path) -> dict[str, Any]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f'cannot decode image: {image_path}')
    annotation = json.loads(annotation_path.read_text(encoding='utf-8'))
    width, height = canonical_size(annotation)
    forward, inverse = homographies(annotation)
    normalized = cv2.warpPerspective(image, forward, (width, height))
    normalized_overlay = normalized.copy()
    original_overlay = image.copy()

    board_source = order_corners(annotation['board_corners']).astype(np.int32).tolist()
    draw_polygon(original_overlay, board_source, COLORS['board'], 'BOARD', 5)

    normalized_regions = annotation['normalized_regions']
    projected_regions: dict[str, Any] = {}
    for name in ['io_rectangle', 'cpu_search_region', 'cpu_socket', 'rear_cpu_bracket']:
        points = normalized_regions.get(name)
        if not points:
            continue
        canonical = normalized_to_pixels(points, width, height)
        projected = project_polygon(canonical, inverse)
        dashed = name == 'rear_cpu_bracket'
        draw_polygon(normalized_overlay, canonical, COLORS[name], LABELS[name], 5, dashed)
        draw_polygon(original_overlay, projected, COLORS[name], LABELS[name], 5, dashed)
        projected_regions[name] = projected

    for name in ['pcie_slots', 'dimm_slots']:
        projected_regions[name] = []
        for index, points in enumerate(normalized_regions.get(name, []), start=1):
            canonical = normalized_to_pixels(points, width, height)
            projected = project_polygon(canonical, inverse)
            label = f"{LABELS[name]} {index}"
            draw_polygon(normalized_overlay, canonical, COLORS[name], label, 4)
            draw_polygon(original_overlay, projected, COLORS[name], label, 4)
            projected_regions[name].append(projected)

    legend = [
        ('PCI-E', COLORS['pcie_slots']), ('DRAM', COLORS['dimm_slots']), ('REAR I/O', COLORS['io_rectangle']),
        ('CPU SEARCH', COLORS['cpu_search_region']), ('EXPECTED SOCKET', COLORS['cpu_socket']),
        ('REAR BRACKET', COLORS['rear_cpu_bracket']),
    ]
    for canvas in [normalized_overlay, original_overlay]:
        x, y = 15, 28
        for text, color in legend:
            cv2.rectangle(canvas, (x, y - 15), (x + 20, y + 5), color, -1)
            cv2.putText(canvas, text, (x + 28, y + 3), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 2, cv2.LINE_AA)
            y += 28

    normalized_output.parent.mkdir(parents=True, exist_ok=True)
    original_output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(normalized_output), normalized_overlay)
    cv2.imwrite(str(original_output), original_overlay)
    return {
        'image': str(image_path),
        'annotation': str(annotation_path),
        'canonical_size': [width, height],
        'board_corners': board_source,
        'homography': forward.tolist(),
        'inverse_homography': inverse.tolist(),
        'projected_regions': projected_regions,
        'normalized_overlay': str(normalized_output),
        'original_overlay': str(original_output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Rectify an angled motherboard photo and render review overlays in normalized and original perspective')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--annotation', type=Path, required=True)
    parser.add_argument('--normalized-output', type=Path, required=True)
    parser.add_argument('--original-output', type=Path, required=True)
    parser.add_argument('--json-output', type=Path, required=True)
    args = parser.parse_args()
    result = render(args.image, args.annotation, args.normalized_output, args.original_output)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'normalized_overlay': result['normalized_overlay'], 'original_overlay': result['original_overlay']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
