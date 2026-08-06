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
    'io_rectangle': (0, 255, 0),
    'pcie_slots': (255, 255, 0),
    'dimm_slots': (255, 0, 255),
    'cpu_search_region': (0, 165, 255),
    'expected_socket': (0, 0, 255),
    'rear_cpu_bracket': (255, 255, 255),
    'observed_socket': (0, 255, 0),
}


def centroid(points: list[list[float]]) -> tuple[float, float]:
    array = np.asarray(points, dtype=np.float32)
    return float(array[:, 0].mean()), float(array[:, 1].mean())


def polygon_distance(left: list[list[float]], right: list[list[float]]) -> float:
    lx, ly = centroid(left)
    rx, ry = centroid(right)
    return float(((lx - rx) ** 2 + (ly - ry) ** 2) ** 0.5)


def draw_polygon(image: np.ndarray, points: list[list[float]], color: tuple[int, int, int], label: str, thickness: int = 4) -> None:
    polygon = np.asarray(points, dtype=np.int32)
    cv2.polylines(image, [polygon], True, color, thickness)
    x, y = tuple(int(v) for v in polygon[0])
    cv2.putText(image, label, (x + 4, max(18, y - 7)), cv2.FONT_HERSHEY_SIMPLEX, .52, color, 2, cv2.LINE_AA)


def status_rows(annotation: dict[str, Any], observed: dict[str, Any] | None) -> list[tuple[str, str]]:
    rows = [
        ('Board', 'PASS' if annotation.get('board') else 'MISSING'),
        ('Rear I/O', 'PASS' if annotation.get('io_rectangle') else 'MISSING'),
        ('PCIe slots', f"PASS ({len(annotation.get('pcie_slots', []))})" if annotation.get('pcie_slots') else 'MISSING'),
        ('DIMM slots', f"PASS ({len(annotation.get('dimm_slots', []))})" if annotation.get('dimm_slots') else 'MISSING'),
        ('CPU search', 'PASS' if annotation.get('cpu_search_region') else 'MISSING'),
        ('Expected socket', 'PASS' if annotation.get('cpu_socket') else 'MISSING'),
        ('Rear bracket', 'PASS' if annotation.get('rear_cpu_bracket') else 'MISSING'),
    ]
    if observed:
        rows.append(('Observed socket', observed.get('state', 'UNKNOWN')))
        rows.append(('Confidence', f"{float(observed.get('confidence') or 0.0) * 100:.1f}%"))
        if annotation.get('cpu_socket') and observed.get('polygon'):
            rows.append(('Socket offset', f"{polygon_distance(annotation['cpu_socket'], observed['polygon']):.1f}px"))
    return rows


def draw_status_panel(image: np.ndarray, rows: list[tuple[str, str]]) -> None:
    panel_width = 300
    row_height = 27
    height = 18 + len(rows) * row_height
    x1 = image.shape[1] - panel_width - 12
    y1 = 12
    cv2.rectangle(image, (x1, y1), (image.shape[1] - 12, y1 + height), (12, 12, 12), -1)
    cv2.rectangle(image, (x1, y1), (image.shape[1] - 12, y1 + height), (220, 220, 220), 1)
    y = y1 + 24
    for name, value in rows:
        cv2.putText(image, name, (x1 + 12, y), cv2.FONT_HERSHEY_SIMPLEX, .48, (225, 225, 225), 1, cv2.LINE_AA)
        color = (60, 220, 120) if value.startswith('PASS') or value in {'EMPTY SOCKET', 'CPU INSTALLED', 'COOLER / OBSCURED'} else (230, 210, 80)
        cv2.putText(image, value, (x1 + 145, y), cv2.FONT_HERSHEY_SIMPLEX, .48, color, 1, cv2.LINE_AA)
        y += row_height


def build_report(image_path: Path, annotation_path: Path, output_path: Path, observed_path: Path | None = None) -> dict[str, Any]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f'cannot decode image: {image_path}')
    annotation = json.loads(annotation_path.read_text(encoding='utf-8'))
    observed = json.loads(observed_path.read_text(encoding='utf-8')) if observed_path else None
    overlay = image.copy()

    for key, label in [('board', 'BOARD'), ('io_rectangle', 'REAR I/O'), ('cpu_search_region', 'CPU SEARCH'), ('cpu_socket', 'EXPECTED SOCKET'), ('rear_cpu_bracket', 'REAR BRACKET')]:
        if annotation.get(key):
            color_key = 'expected_socket' if key == 'cpu_socket' else key
            draw_polygon(overlay, annotation[key], COLORS[color_key], label, 5)
    for index, points in enumerate(annotation.get('pcie_slots', []), start=1):
        draw_polygon(overlay, points, COLORS['pcie_slots'], f'PCIe {index}', 4)
    for index, points in enumerate(annotation.get('dimm_slots', []), start=1):
        draw_polygon(overlay, points, COLORS['dimm_slots'], f'DIMM {index}', 4)
    if observed and observed.get('polygon'):
        draw_polygon(overlay, observed['polygon'], COLORS['observed_socket'], f"OBSERVED: {observed.get('state', 'UNKNOWN')}", 5)

    rows = status_rows(annotation, observed)
    draw_status_panel(overlay, rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), overlay)
    result = {
        'image': str(image_path),
        'annotation': str(annotation_path),
        'observed': str(observed_path) if observed_path else None,
        'overlay': str(output_path),
        'status': dict(rows),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate a motherboard layout review image with a status panel')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--annotation', type=Path, required=True)
    parser.add_argument('--observed', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--result-json', type=Path)
    args = parser.parse_args()
    result = build_report(args.image, args.annotation, args.output, args.observed)
    if args.result_json:
        args.result_json.parent.mkdir(parents=True, exist_ok=True)
        args.result_json.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
