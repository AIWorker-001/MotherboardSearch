#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

try:
    from .motherboard_kb import load_catalog, model_key, project_region, save_catalog
except ImportError:
    from motherboard_kb import load_catalog, model_key, project_region, save_catalog


def normalize_polygon(points: list[list[float]], width: int, height: int) -> list[list[float]]:
    if width <= 0 or height <= 0:
        raise ValueError('reference dimensions must be positive')
    if len(points) < 3:
        raise ValueError('region polygon requires at least three points')
    normalized = []
    for x, y in points:
        if x < 0 or y < 0 or x > width or y > height:
            raise ValueError('region point lies outside reference image')
        normalized.append([round(float(x) / width, 6), round(float(y) / height, 6)])
    return normalized


def denormalize_polygon(points: list[list[float]], width: int, height: int) -> list[list[float]]:
    return [[float(x) * width, float(y) * height] for x, y in points]


def set_region(
    catalog: dict[str, Any],
    *,
    model: str,
    name: str,
    points: list[list[float]],
    reference_width: int,
    reference_height: int,
    reference_id: str | None = None,
) -> dict[str, Any]:
    key = model_key(model)
    board = catalog.get('boards', {}).get(key)
    if board is None:
        raise KeyError(f'board not found: {model}')
    region = {
        'name': name,
        'polygon_normalized': normalize_polygon(points, reference_width, reference_height),
        'reference_size': [reference_width, reference_height],
        'reference_id': reference_id,
    }
    board.setdefault('regions', {})[name] = region
    return region


def projected_regions(board: dict[str, Any], best_match: dict[str, Any]) -> dict[str, list[list[float]]]:
    homography = best_match.get('homography')
    reference_size = best_match.get('reference_size')
    if not homography or not reference_size:
        return {}
    width, height = int(reference_size[0]), int(reference_size[1])
    output = {}
    for name, region in (board.get('regions') or {}).items():
        reference_id = region.get('reference_id')
        if reference_id and reference_id != best_match.get('reference_id'):
            continue
        polygon = denormalize_polygon(region['polygon_normalized'], width, height)
        output[name] = project_region(polygon, homography)
    return output


def polygon_bounds(points: list[list[float]], image_size: tuple[int, int], padding: float = 0.10) -> tuple[int, int, int, int]:
    width, height = image_size
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    pad_x = max(4.0, (x2 - x1) * padding)
    pad_y = max(4.0, (y2 - y1) * padding)
    return (
        max(0, int(x1 - pad_x)),
        max(0, int(y1 - pad_y)),
        min(width, int(x2 + pad_x)),
        min(height, int(y2 + pad_y)),
    )


def write_region_crops(image_path: Path, regions: dict[str, list[list[float]]], output_dir: Path) -> list[dict[str, Any]]:
    image = Image.open(image_path).convert('RGB')
    rows = []
    for name, polygon in regions.items():
        bounds = polygon_bounds(polygon, image.size)
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            continue
        crop_path = output_dir / f'{name}.jpg'
        overlay_path = output_dir / f'{name}-overlay.jpg'
        crop_path.parent.mkdir(parents=True, exist_ok=True)
        image.crop(bounds).save(crop_path, quality=92)
        overlay = image.copy()
        ImageDraw.Draw(overlay).polygon([(float(x), float(y)) for x, y in polygon], outline='red', width=5)
        overlay.save(overlay_path, quality=90)
        rows.append({'name': name, 'polygon': polygon, 'bounds': list(bounds), 'crop': str(crop_path), 'overlay': str(overlay_path)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description='Manage motherboard component regions and project them into listing photos')
    sub = parser.add_subparsers(dest='command', required=True)
    define = sub.add_parser('set')
    define.add_argument('--catalog', type=Path, default=Path('data/motherboard_kb/catalog.json'))
    define.add_argument('--model', required=True)
    define.add_argument('--name', required=True)
    define.add_argument('--points', required=True, help='JSON polygon, e.g. [[10,20],[100,20],[100,120],[10,120]]')
    define.add_argument('--reference-width', type=int, required=True)
    define.add_argument('--reference-height', type=int, required=True)
    define.add_argument('--reference-id')
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    region = set_region(
        catalog,
        model=args.model,
        name=args.name,
        points=json.loads(args.points),
        reference_width=args.reference_width,
        reference_height=args.reference_height,
        reference_id=args.reference_id,
    )
    save_catalog(args.catalog, catalog)
    print(json.dumps(region, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
