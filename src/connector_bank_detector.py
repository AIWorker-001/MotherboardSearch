#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    from .connector_line_detector import angle_distance, detect_connector_candidates
except ImportError:
    from connector_line_detector import angle_distance, detect_connector_candidates


def candidate_axis(candidate: dict[str, Any]) -> np.ndarray:
    angle = math.radians(float(candidate['angle']))
    return np.asarray([math.cos(angle), math.sin(angle)], dtype=np.float32)


def candidate_normal(candidate: dict[str, Any]) -> np.ndarray:
    axis = candidate_axis(candidate)
    return np.asarray([-axis[1], axis[0]], dtype=np.float32)


def group_candidates(candidates: list[dict[str, Any]], image_shape: tuple[int, int, int]) -> list[list[dict[str, Any]]]:
    height, width = image_shape[:2]
    short_side = min(width, height)
    groups: list[list[dict[str, Any]]] = []
    for candidate in sorted(candidates, key=lambda row: row['score'], reverse=True):
        center = np.asarray(candidate['center'], dtype=np.float32)
        placed = False
        for group in groups:
            mean_angle = sum(float(row['angle']) for row in group) / len(group)
            if angle_distance(float(candidate['angle']), mean_angle) > 6.0:
                continue
            axis = np.asarray([math.cos(math.radians(mean_angle)), math.sin(math.radians(mean_angle))], dtype=np.float32)
            normal = np.asarray([-axis[1], axis[0]], dtype=np.float32)
            group_centers = [np.asarray(row['center'], dtype=np.float32) for row in group]
            normal_distance = min(abs(float(np.dot(center - other, normal))) for other in group_centers)
            axis_distance = min(abs(float(np.dot(center - other, axis))) for other in group_centers)
            mean_length = sum(float(row['length']) for row in group) / len(group)
            if normal_distance <= short_side * 0.18 and axis_distance <= mean_length * 0.85:
                group.append(candidate)
                placed = True
                break
        if not placed:
            groups.append([candidate])
    return groups


def dedupe_group(group: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for candidate in sorted(group, key=lambda row: row['score'], reverse=True):
        center = np.asarray(candidate['center'], dtype=np.float32)
        if any(np.linalg.norm(center - np.asarray(other['center'], dtype=np.float32)) < 18 for other in kept):
            continue
        kept.append(candidate)
    return kept


def spacing_stats(group: list[dict[str, Any]]) -> tuple[float, float]:
    if len(group) < 2:
        return 0.0, 1.0
    mean_angle = sum(float(row['angle']) for row in group) / len(group)
    axis = np.asarray([math.cos(math.radians(mean_angle)), math.sin(math.radians(mean_angle))], dtype=np.float32)
    normal = np.asarray([-axis[1], axis[0]], dtype=np.float32)
    offsets = sorted(float(np.dot(np.asarray(row['center'], dtype=np.float32), normal)) for row in group)
    gaps = [offsets[index + 1] - offsets[index] for index in range(len(offsets) - 1)]
    if not gaps:
        return 0.0, 1.0
    median = float(np.median(gaps))
    variation = float(np.std(gaps) / max(1e-6, median))
    return median, variation


def bounding_box(group: list[dict[str, Any]]) -> list[int]:
    xs = [point[0] for row in group for point in row['polygon']]
    ys = [point[1] for row in group for point in row['polygon']]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def classify_group(group: list[dict[str, Any]], image_shape: tuple[int, int, int]) -> dict[str, Any]:
    height, width = image_shape[:2]
    group = dedupe_group(group)
    count = len(group)
    lengths = np.asarray([float(row['length']) for row in group], dtype=np.float32)
    widths = np.asarray([float(row['width']) for row in group], dtype=np.float32)
    median_length = float(np.median(lengths)) if count else 0.0
    length_cv = float(np.std(lengths) / max(1e-6, np.mean(lengths))) if count else 1.0
    width_cv = float(np.std(widths) / max(1e-6, np.mean(widths))) if count else 1.0
    spacing, spacing_cv = spacing_stats(group)
    box = bounding_box(group) if group else [0, 0, 0, 0]
    center_x = (box[0] + box[2]) / (2.0 * width)
    center_y = (box[1] + box[3]) / (2.0 * height)
    long_fraction = float(np.mean(lengths >= median_length * 0.82)) if count else 0.0
    short_fraction = float(np.mean(lengths <= median_length * 0.62)) if count else 0.0
    angle = sum(float(row['angle']) for row in group) / max(1, count)

    dimm_score = 0.0
    dimm_score += 0.28 * max(0.0, 1.0 - abs(count - 4) / 3.0)
    dimm_score += 0.24 * max(0.0, 1.0 - length_cv / 0.35)
    dimm_score += 0.16 * max(0.0, 1.0 - width_cv / 0.45)
    dimm_score += 0.20 * max(0.0, 1.0 - spacing_cv / 0.55)
    dimm_score += 0.12 * max(0.0, min(1.0, (center_x - 0.42) / 0.38))

    pcie_score = 0.0
    pcie_score += 0.22 * max(0.0, min(1.0, (count - 2) / 4.0))
    pcie_score += 0.18 * max(0.0, 1.0 - spacing_cv / 0.80)
    pcie_score += 0.22 * max(0.0, min(1.0, (0.58 - center_x) / 0.45))
    pcie_score += 0.12 * max(0.0, min(1.0, (0.72 - center_y) / 0.55))
    pcie_score += 0.14 * min(1.0, long_fraction + short_fraction)
    pcie_score += 0.12 * max(0.0, 1.0 - width_cv / 0.65)

    label = 'unknown'
    if dimm_score >= 0.58 and dimm_score > pcie_score + 0.08:
        label = 'dimm_bank'
    elif pcie_score >= 0.50:
        label = 'pcie_bank'

    return {
        'label': label,
        'count': count,
        'angle': round(angle, 2),
        'box': box,
        'center_normalized': [round(center_x, 4), round(center_y, 4)],
        'median_length': round(median_length, 2),
        'length_cv': round(length_cv, 4),
        'width_cv': round(width_cv, 4),
        'median_spacing': round(spacing, 2),
        'spacing_cv': round(spacing_cv, 4),
        'pcie_score': round(pcie_score, 4),
        'dimm_score': round(dimm_score, 4),
        'members': group,
    }


def detect_banks(image: np.ndarray, config: dict[str, Any]) -> dict[str, Any]:
    candidates = detect_connector_candidates(image, config.get('candidate_detector', {}))
    raw_groups = group_candidates(candidates, image.shape)
    classified = [classify_group(group, image.shape) for group in raw_groups if len(group) >= 2]
    classified.sort(key=lambda row: max(row['pcie_score'], row['dimm_score']), reverse=True)
    pcie = next((row for row in classified if row['label'] == 'pcie_bank'), None)
    dimm = next((row for row in classified if row['label'] == 'dimm_bank'), None)
    return {'candidates': candidates, 'groups': classified, 'pcie_bank': pcie, 'dimm_bank': dimm}


def draw_overlay(image: np.ndarray, result: dict[str, Any]) -> np.ndarray:
    overlay = image.copy()
    for name, color in [('pcie_bank', (0, 255, 0)), ('dimm_bank', (0, 255, 255))]:
        bank = result.get(name)
        if not bank:
            continue
        x1, y1, x2, y2 = bank['box']
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 5)
        cv2.putText(overlay, f"{name.upper()} score={max(bank['pcie_score'], bank['dimm_score']):.2f}", (x1 + 5, max(25, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, .72, color, 2, cv2.LINE_AA)
        for index, member in enumerate(bank['members'], start=1):
            points = np.asarray(member['polygon'], dtype=np.int32)
            cv2.polylines(overlay, [points], True, color, 3, cv2.LINE_AA)
            x, y = [int(v) for v in member['center']]
            cv2.putText(overlay, str(index), (x + 3, y - 3), cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2, cv2.LINE_AA)
    return overlay


def main() -> int:
    parser = argparse.ArgumentParser(description='Identify PCIe and DIMM connector banks from raw connector candidates')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('config/connector_bank_detector.json'))
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    image = cv2.imread(str(args.image))
    if image is None:
        raise ValueError(f'cannot decode image: {args.image}')
    config = json.loads(args.config.read_text(encoding='utf-8'))
    result = detect_banks(image, config)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = args.output_dir / 'connector-banks-overlay.jpg'
    report_path = args.output_dir / 'connector-banks.json'
    cv2.imwrite(str(overlay_path), draw_overlay(image, result))
    report_path.write_text(json.dumps({**result, 'overlay': str(overlay_path)}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'pcie_found': result['pcie_bank'] is not None,
        'dimm_found': result['dimm_bank'] is not None,
        'pcie_score': None if result['pcie_bank'] is None else result['pcie_bank']['pcie_score'],
        'dimm_score': None if result['dimm_bank'] is None else result['dimm_bank']['dimm_score'],
        'overlay': str(overlay_path),
        'report': str(report_path),
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
