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
except ImportError:
    from motherboard_kb import load_catalog, model_key, save_catalog
    from reference_regions import normalize_polygon

COLORS = {
    'board': (255, 0, 0),
    'io_rectangle': (0, 255, 0),
    'pcie_slots': (255, 255, 0),
    'dimm_slots': (255, 0, 255),
    'cpu_search_region': (0, 165, 255),
    'cpu_socket': (0, 0, 255),
    'rear_cpu_bracket': (255, 255, 255),
}
LABELS = {
    'board': 'BOARD',
    'io_rectangle': 'REAR I/O',
    'pcie_slots': 'PCIe',
    'dimm_slots': 'DIMM',
    'cpu_search_region': 'CPU SEARCH',
    'cpu_socket': 'CPU SOCKET',
    'rear_cpu_bracket': 'REAR BRACKET',
}


def validate_polygon(points: list[list[float]], width: int, height: int, name: str) -> None:
    if len(points) < 3:
        raise ValueError(f'{name} requires at least three points')
    for x, y in points:
        if not 0 <= float(x) <= width or not 0 <= float(y) <= height:
            raise ValueError(f'{name} point {(x, y)} is outside {width}x{height}')


def _draw_polygon(image: np.ndarray, points: list[list[float]], color: tuple[int, int, int], label: str, thickness: int = 4) -> None:
    polygon = np.asarray(points, dtype=np.int32)
    cv2.polylines(image, [polygon], True, color, thickness)
    anchor = tuple(int(value) for value in polygon[np.argmin(polygon[:, 0] + polygon[:, 1])])
    x, y = anchor
    cv2.putText(image, label, (x + 5, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2, cv2.LINE_AA)


def _legend(image: np.ndarray, annotation: dict[str, Any]) -> None:
    entries = []
    for key in ['board', 'io_rectangle', 'pcie_slots', 'dimm_slots', 'cpu_search_region', 'cpu_socket', 'rear_cpu_bracket']:
        value = annotation.get(key)
        if value:
            entries.append((key, LABELS[key]))
    if not entries:
        return
    x, y = 18, 28
    box_width = 235
    box_height = 12 + len(entries) * 28
    cv2.rectangle(image, (8, 8), (8 + box_width, 8 + box_height), (15, 15, 15), -1)
    cv2.rectangle(image, (8, 8), (8 + box_width, 8 + box_height), (210, 210, 210), 1)
    for key, label in entries:
        color = COLORS[key]
        cv2.line(image, (x, y), (x + 28, y), color, 5)
        cv2.putText(image, label, (x + 38, y + 5), cv2.FONT_HERSHEY_SIMPLEX, .52, (240, 240, 240), 1, cv2.LINE_AA)
        y += 28


def annotate_reference(image_path: Path, annotation_path: Path, output_path: Path) -> dict[str, Any]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f'cannot decode image: {image_path}')
    height, width = image.shape[:2]
    annotation = json.loads(annotation_path.read_text(encoding='utf-8'))
    overlay = image.copy()

    for name in ['board', 'io_rectangle', 'cpu_search_region', 'cpu_socket', 'rear_cpu_bracket']:
        points = annotation.get(name)
        if not points:
            continue
        validate_polygon(points, width, height, name)
        _draw_polygon(overlay, points, COLORS[name], LABELS[name], 5)

    for name in ['pcie_slots', 'dimm_slots']:
        for index, points in enumerate(annotation.get(name, []), start=1):
            validate_polygon(points, width, height, f'{name}[{index}]')
            _draw_polygon(overlay, points, COLORS[name], f'{LABELS[name]} {index}', 4)

    _legend(overlay, annotation)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), overlay)
    return {
        'image': str(image_path),
        'image_size': [width, height],
        'annotation': annotation,
        'overlay': str(output_path),
        'checks': {
            'board': bool(annotation.get('board')),
            'io_rectangle': bool(annotation.get('io_rectangle')),
            'pcie_slots': len(annotation.get('pcie_slots', [])),
            'dimm_slots': len(annotation.get('dimm_slots', [])),
            'cpu_search_region': bool(annotation.get('cpu_search_region')),
            'cpu_socket': bool(annotation.get('cpu_socket')),
            'rear_cpu_bracket': bool(annotation.get('rear_cpu_bracket')),
        },
    }


def write_to_catalog(catalog_path: Path, model: str, reference_id: str, result: dict[str, Any]) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    key = model_key(model)
    board = catalog.get('boards', {}).get(key)
    if board is None:
        raise KeyError(f'board not found: {model}')
    width, height = result['image_size']
    annotation = result['annotation']
    layout = {
        'reference_id': reference_id,
        'source': 'manual_reference_annotation_v2',
        'image_size': [width, height],
        'board_polygon_normalized': normalize_polygon(annotation['board'], width, height),
        'io_rectangle_normalized': normalize_polygon(annotation['io_rectangle'], width, height) if annotation.get('io_rectangle') else None,
        'cpu_search_region_normalized': normalize_polygon(annotation['cpu_search_region'], width, height),
        'pcie_slots_normalized': [normalize_polygon(points, width, height) for points in annotation.get('pcie_slots', [])],
        'dimm_slots_normalized': [normalize_polygon(points, width, height) for points in annotation.get('dimm_slots', [])],
        'rear_cpu_bracket_normalized': normalize_polygon(annotation['rear_cpu_bracket'], width, height) if annotation.get('rear_cpu_bracket') else None,
    }
    board['layout'] = layout
    board.setdefault('regions', {})['cpu_socket'] = {
        'name': 'cpu_socket',
        'polygon_normalized': normalize_polygon(annotation['cpu_socket'], width, height),
        'reference_size': [width, height],
        'reference_id': reference_id,
        'derived_by': 'manual_reference_annotation_v2',
    }
    save_catalog(catalog_path, catalog)
    return board


def main() -> int:
    parser = argparse.ArgumentParser(description='Create a verified motherboard layout overlay and optionally store normalized landmarks')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--annotation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--result-json', type=Path)
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--model')
    parser.add_argument('--reference-id')
    args = parser.parse_args()
    result = annotate_reference(args.image, args.annotation, args.output)
    if args.catalog or args.model or args.reference_id:
        if not (args.catalog and args.model and args.reference_id):
            raise ValueError('--catalog, --model, and --reference-id must be supplied together')
        write_to_catalog(args.catalog, args.model, args.reference_id, result)
    if args.result_json:
        args.result_json.parent.mkdir(parents=True, exist_ok=True)
        args.result_json.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
