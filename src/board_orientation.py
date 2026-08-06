#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    from .slot_geometry import classify_slot_banks
except ImportError:
    from slot_geometry import classify_slot_banks

ROTATIONS = {
    0: None,
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def rotate_image(image: np.ndarray, degrees: int) -> np.ndarray:
    code = ROTATIONS[degrees]
    return image.copy() if code is None else cv2.rotate(image, code)


def _normalized_center(box: list[float], width: int, height: int) -> tuple[float, float]:
    x1, y1, x2, y2 = [float(v) for v in box]
    return ((x1 + x2) / (2.0 * width), (y1 + y2) / (2.0 * height))


def score_orientation(image: np.ndarray, config: dict[str, Any]) -> dict[str, Any]:
    height, width = image.shape[:2]
    board_box = (0, 0, width, height)
    slots = classify_slot_banks(image, board_box, config.get('slot_geometry', {}))
    dimm = slots.get('dimm_bank')
    pcie = slots.get('pcie_bank')
    score = 0.0
    reasons: list[str] = []

    if pcie:
        pcie_x, pcie_y = _normalized_center(pcie['box'], width, height)
        left_score = max(0.0, min(1.0, (0.58 - pcie_x) / 0.38))
        upper_score = max(0.0, min(1.0, (0.68 - pcie_y) / 0.48))
        count_score = min(1.0, float(pcie.get('count', 0)) / 3.0)
        score += left_score * 0.42 + upper_score * 0.16 + count_score * 0.12
        reasons.append(f'pcie_center=({pcie_x:.3f},{pcie_y:.3f})')
        reasons.append(f'pcie_count={pcie.get("count", 0)}')
    else:
        reasons.append('pcie_not_found')

    if dimm:
        dimm_x, dimm_y = _normalized_center(dimm['box'], width, height)
        inward_right = max(0.0, min(1.0, (dimm_x - 0.42) / 0.42))
        lower_score = max(0.0, min(1.0, (dimm_y - 0.40) / 0.45))
        score += inward_right * 0.20 + lower_score * 0.10
        reasons.append(f'dimm_center=({dimm_x:.3f},{dimm_y:.3f})')
    else:
        reasons.append('dimm_not_found')

    if pcie and dimm:
        pcie_x, _ = _normalized_center(pcie['box'], width, height)
        dimm_x, _ = _normalized_center(dimm['box'], width, height)
        if dimm_x > pcie_x:
            score += 0.10
            reasons.append('dimm_right_of_pcie')
        else:
            score -= 0.10
            reasons.append('dimm_not_right_of_pcie')

    return {
        'score': round(max(0.0, min(1.0, score)), 4),
        'pcie_bank': pcie,
        'dimm_bank': dimm,
        'reasons': reasons,
    }


def evaluate_rotations(image: np.ndarray, config: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for degrees in (0, 90, 180, 270):
        rotated = rotate_image(image, degrees)
        result = score_orientation(rotated, config)
        rows.append({
            'rotation': degrees,
            'size': [rotated.shape[1], rotated.shape[0]],
            **result,
        })
    return sorted(rows, key=lambda row: row['score'], reverse=True)


def draw_orientation_overlay(image: np.ndarray, result: dict[str, Any]) -> np.ndarray:
    overlay = image.copy()
    for name, color in [('pcie_bank', (0, 255, 0)), ('dimm_bank', (0, 255, 255))]:
        bank = result.get(name)
        if not bank:
            continue
        x1, y1, x2, y2 = [int(v) for v in bank['box']]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 5)
        cv2.putText(overlay, name.replace('_bank', '').upper(), (x1 + 5, max(24, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, .8, color, 2, cv2.LINE_AA)
    cv2.putText(overlay, f"Rotation {result['rotation']} deg score {result['score']:.3f}", (18, 32), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2, cv2.LINE_AA)
    return overlay


def main() -> int:
    parser = argparse.ArgumentParser(description='Evaluate all four normalized-board rotations and choose the canonical ATX orientation')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('config/board_orientation.json'))
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    image = cv2.imread(str(args.image))
    if image is None:
        raise ValueError(f'cannot decode image: {args.image}')
    config = json.loads(args.config.read_text(encoding='utf-8'))
    results = evaluate_rotations(image, config)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for row in results:
        rotated = rotate_image(image, int(row['rotation']))
        cv2.imwrite(str(args.output_dir / f'orientation-{row["rotation"]}.jpg'), draw_orientation_overlay(rotated, row))
    best = results[0]
    canonical = rotate_image(image, int(best['rotation']))
    canonical_path = args.output_dir / 'board-canonical.jpg'
    cv2.imwrite(str(canonical_path), canonical)
    payload = {
        'image': str(args.image),
        'selected_rotation': best['rotation'],
        'selected_score': best['score'],
        'canonical_image': str(canonical_path),
        'results': results,
    }
    (args.output_dir / 'board-orientation.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
