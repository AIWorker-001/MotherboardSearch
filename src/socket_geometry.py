#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def entropy(gray: np.ndarray) -> float:
    hist = cv2.calcHist([gray], [0], None, [64], [0, 256]).ravel()
    probabilities = hist / max(1.0, hist.sum())
    probabilities = probabilities[probabilities > 0]
    return float(-(probabilities * np.log2(probabilities)).sum())


def orientation_balance(gray: np.ndarray) -> float:
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    horizontal = float(np.mean(np.abs(gx)))
    vertical = float(np.mean(np.abs(gy)))
    if max(horizontal, vertical) <= 1e-6:
        return 0.0
    return min(horizontal, vertical) / max(horizontal, vertical)


def center_frame_contrast(gray: np.ndarray) -> float:
    height, width = gray.shape
    if min(height, width) < 24:
        return 0.0
    center = gray[int(height * .28):int(height * .72), int(width * .28):int(width * .72)]
    mask = np.ones(gray.shape, dtype=np.uint8)
    mask[int(height * .18):int(height * .82), int(width * .18):int(width * .82)] = 0
    frame = gray[mask.astype(bool)]
    if center.size == 0 or frame.size == 0:
        return 0.0
    return min(1.0, abs(float(center.mean()) - float(frame.mean())) / 64.0)


def periodic_pin_score(gray: np.ndarray) -> float:
    normalized = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_AREA)
    normalized = normalized.astype(np.float32) - float(normalized.mean())
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(normalized)))
    cy, cx = 64, 64
    y, x = np.ogrid[:128, :128]
    radius = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    band = spectrum[(radius >= 10) & (radius <= 42)]
    total = spectrum[(radius >= 3) & (radius <= 55)]
    if total.size == 0 or float(total.mean()) <= 1e-6:
        return 0.0
    peak = float(np.percentile(band, 97))
    baseline = float(np.median(total)) + 1e-6
    return min(1.0, max(0.0, (peak / baseline - 2.0) / 10.0))


def candidate_metrics(gray: np.ndarray, edges: np.ndarray, box: tuple[int, int, int, int], image_size: tuple[int, int]) -> dict[str, float]:
    x, y, width, height = box
    roi = gray[y:y + height, x:x + width]
    roi_edges = edges[y:y + height, x:x + width]
    image_width, image_height = image_size
    edge_density = float(np.mean(roi_edges > 0))
    texture = min(1.0, float(cv2.Laplacian(roi, cv2.CV_64F).var()) / 5000.0)
    balance = orientation_balance(roi)
    contrast = center_frame_contrast(roi)
    periodicity = periodic_pin_score(roi)
    aspect = width / max(1.0, float(height))
    square = math.exp(-abs(math.log(max(aspect, 1e-6))) * 1.7)
    cx = (x + width / 2) / image_width
    cy = (y + height / 2) / image_height
    center_prior = max(0.0, 1.0 - math.sqrt(((cx - .5) / .72) ** 2 + ((cy - .46) / .72) ** 2))
    score = (
        edge_density * .18
        + texture * .18
        + balance * .15
        + contrast * .12
        + periodicity * .25
        + square * .07
        + center_prior * .05
    )
    return {
        'score': round(score, 4),
        'edge_density': round(edge_density, 4),
        'texture': round(texture, 4),
        'orientation_balance': round(balance, 4),
        'center_frame_contrast': round(contrast, 4),
        'periodic_pin_score': round(periodicity, 4),
        'square_score': round(square, 4),
        'center_prior': round(center_prior, 4),
    }


def rectangle_candidates(image: np.ndarray, config: dict[str, Any]) -> list[dict[str, Any]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    edges = cv2.Canny(gray, int(config.get('canny_low', 55)), int(config.get('canny_high', 150)))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_height, image_width = gray.shape
    image_area = image_width * image_height
    minimum = float(config.get('minimum_area_ratio', .006))
    maximum = float(config.get('maximum_area_ratio', .09))
    candidates: list[dict[str, Any]] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area_ratio = width * height / image_area
        aspect = width / max(1.0, float(height))
        if not minimum <= area_ratio <= maximum or not .58 <= aspect <= 1.72:
            continue
        perimeter = cv2.arcLength(contour, True)
        approximate = cv2.approxPolyDP(contour, .035 * perimeter, True)
        if not 4 <= len(approximate) <= 12:
            continue
        metrics = candidate_metrics(gray, edges, (x, y, width, height), (image_width, image_height))
        candidates.append({
            'box': [x, y, x + width, y + height],
            'area_ratio': round(area_ratio, 5),
            'aspect_ratio': round(aspect, 4),
            'vertices': len(approximate),
            **metrics,
        })
    deduplicated = []
    for candidate in sorted(candidates, key=lambda row: row['score'], reverse=True):
        x1, y1, x2, y2 = candidate['box']
        keep = True
        for prior in deduplicated:
            px1, py1, px2, py2 = prior['box']
            intersection = max(0, min(x2, px2) - max(x1, px1)) * max(0, min(y2, py2) - max(y1, py1))
            union = (x2 - x1) * (y2 - y1) + (px2 - px1) * (py2 - py1) - intersection
            if union and intersection / union > .45:
                keep = False
                break
        if keep:
            deduplicated.append(candidate)
    return deduplicated[: int(config.get('maximum_candidates', 20))]


def detect_empty_lga(image_path: Path, config: dict[str, Any], artifact_path: Path | None = None) -> dict[str, Any]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f'cannot decode image: {image_path}')
    candidates = rectangle_candidates(image, config)
    best = candidates[0] if candidates else None
    minimum_score = float(config.get('minimum_empty_lga_score', .55))
    minimum_periodicity = float(config.get('minimum_periodic_pin_score', .32))
    detected = bool(best and best['score'] >= minimum_score and best['periodic_pin_score'] >= minimum_periodicity)
    if artifact_path:
        overlay = image.copy()
        for index, candidate in enumerate(candidates[:8]):
            x1, y1, x2, y2 = candidate['box']
            thickness = 5 if index == 0 else 2
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), thickness)
            cv2.putText(overlay, f"{index + 1}:{candidate['score']:.2f}/{candidate['periodic_pin_score']:.2f}", (x1, max(18, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 255), 1, cv2.LINE_AA)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(artifact_path), overlay)
    return {
        'image': str(image_path),
        'detected': detected,
        'state': 'empty_intel_lga_socket' if detected else 'not_confirmed',
        'confidence': 0.0 if not best else best['score'],
        'best_candidate': best,
        'candidates': candidates,
        'artifact': str(artifact_path) if artifact_path else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Detect an empty Intel LGA socket from rectangle and pin-texture geometry')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('config/socket_geometry.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--artifact', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    result = detect_empty_lga(args.image, config, args.artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'detected': result['detected'], 'confidence': result['confidence']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
