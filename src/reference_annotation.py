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
    'pcie_slots': (255, 255, 0),
    'dimm_slots': (0, 255, 255),
    'cpu_socket': (255, 0, 255),
    'cpu_search_region': (0, 165, 255),
}


def validate_polygon(points: list[list[float]], width: int, height: int, name: str) -> None:
    if len(points) < 3:
        raise ValueError(f'{name} requires at least three points')
    for x, y in points:
        if not 0 <= float(x) <= width or not 0 <= float(y) <= height:
            raise ValueError(f'{name} point {(x, y)} is outside {width}x{height}')


def annotate_reference(image_path: Path, annotation_path: Path, output_path: Path) -> dict[str, Any]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f'cannot decode image: {image_path}')
    height, width = image.shape[:2]
    annotation = json.loads(annotation_path.read_text(encoding='utf-8'))
    overlay = image.copy()
    for name in ['board', 'cpu_search_region', 'cpu_socket']:
        points = annotation.get(name)
        if not points:
            continue
        validate_polygon(points, width, height, name)
        cv2.polylines(overlay, [np.asarray(points, dtype=np.int32)], True, COLORS[name], 5)
    for name in ['pcie_slots', 'dimm_slots']:
        for index, points in enumerate(annotation.get(name, []), start=1):
            validate_polygon(points, width, height, f'{name}[{index}]')
            cv2.polylines(overlay, [np.asarray(points, dtype=np.int32)], True, COLORS[name], 4)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), overlay)
    return {
        'image': str(image_path),
        'image_size': [width, height],
        'annotation': annotation,
        'overlay': str(output_path),
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
        'source': 'manual_reference_annotation_v1',
        'image_size': [width, height],
        'board_polygon_normalized': normalize_polygon(annotation['board'], width, height),
        'cpu_search_region_normalized': normalize_polygon(annotation['cpu_search_region'], width, height),
        'pcie_slots_normalized': [normalize_polygon(points, width, height) for points in annotation.get('pcie_slots', [])],
        'dimm_slots_normalized': [normalize_polygon(points, width, height) for points in annotation.get('dimm_slots', [])],
    }
    board['layout'] = layout
    board.setdefault('regions', {})['cpu_socket'] = {
        'name': 'cpu_socket',
        'polygon_normalized': normalize_polygon(annotation['cpu_socket'], width, height),
        'reference_size': [width, height],
        'reference_id': reference_id,
        'derived_by': 'manual_reference_annotation_v1',
    }
    save_catalog(catalog_path, catalog)
    return board


def main() -> int:
    parser = argparse.ArgumentParser(description='Create a verified reference overlay and optionally store landmarks in the motherboard catalog')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--annotation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--model')
    parser.add_argument('--reference-id')
    args = parser.parse_args()
    result = annotate_reference(args.image, args.annotation, args.output)
    if args.catalog or args.model or args.reference_id:
        if not (args.catalog and args.model and args.reference_id):
            raise ValueError('--catalog, --model, and --reference-id must be supplied together')
        write_to_catalog(args.catalog, args.model, args.reference_id, result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
