#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def order_quad(points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(-1)
    return np.asarray([
        pts[np.argmin(sums)],
        pts[np.argmin(diffs)],
        pts[np.argmax(sums)],
        pts[np.argmax(diffs)],
    ], dtype=np.float32)


def quad_dimensions(quad: np.ndarray) -> tuple[int, int]:
    tl, tr, br, bl = order_quad(quad)
    width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    return max(1, int(round(width))), max(1, int(round(height)))


def _score_candidate(contour: np.ndarray, quad: np.ndarray, image_area: float) -> float:
    area = abs(cv2.contourArea(quad.astype(np.float32)))
    if area <= 0:
        return 0.0
    contour_area = abs(cv2.contourArea(contour))
    fill = min(1.0, contour_area / area)
    area_ratio = area / max(1.0, image_area)
    width, height = quad_dimensions(quad)
    aspect = max(width, height) / max(1.0, min(width, height))
    atx_prior = max(0.0, 1.0 - abs(aspect - 1.25) / 0.75)
    return area_ratio * 0.65 + fill * 0.20 + atx_prior * 0.15


def detect_board_quad(image: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    edges = cv2.Canny(blur, 35, 110)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    closed = cv2.dilate(closed, np.ones((5, 5), np.uint8), iterations=1)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(image.shape[0] * image.shape[1])
    candidates: list[dict[str, Any]] = []
    for contour in contours:
        contour_area = abs(cv2.contourArea(contour))
        if contour_area / image_area < 0.18:
            continue
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        for epsilon in (0.015, 0.02, 0.03, 0.04):
            approx = cv2.approxPolyDP(hull, epsilon * perimeter, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                quad = order_quad(approx.reshape(4, 2))
                score = _score_candidate(contour, quad, image_area)
                candidates.append({'quad': quad, 'score': score, 'method': f'approx_{epsilon:.3f}'})
                break
        rect = cv2.minAreaRect(hull)
        quad = order_quad(cv2.boxPoints(rect))
        score = _score_candidate(contour, quad, image_area) * 0.90
        candidates.append({'quad': quad, 'score': score, 'method': 'min_area_rect'})
    if not candidates:
        raise RuntimeError('no plausible motherboard quadrilateral found')
    best = max(candidates, key=lambda row: row['score'])
    raw_quad = np.rint(best['quad']).astype(int).tolist()
    repair = infer_top_right_from_top_edge(raw_quad, (image.shape[1], image.shape[0]))
    final_quad = repair.get('quad', raw_quad)
    return {
        'quad': final_quad,
        'raw_quad': raw_quad,
        'top_right_repair': repair,
        'score': round(float(best['score']), 4),
        'method': best['method'],
        'candidate_count': len(candidates),
    }



def infer_top_right_from_top_edge(quad: list[list[float]], image_size: tuple[int, int], minimum_inset_ratio: float = 0.04) -> dict[str, Any]:
    """Repair a top-right point captured on raised rear-I/O hardware.

    The visible PCB top edge is represented by TL -> observed TR. If observed TR
    stops materially before the lower-right PCB edge, extend that straight top
    edge until it reaches the right PCB boundary (approximated by BR.x). This is
    intentionally conservative and only activates for a substantial horizontal
    inset.
    """
    ordered = order_quad(np.asarray(quad, dtype=np.float32))
    tl, observed_tr, br, bl = ordered
    board_width = max(1.0, float(np.linalg.norm(br - bl)))
    inset = float(br[0] - observed_tr[0])
    result = {
        'applied': False,
        'reason': 'top_right_not_materially_inset',
        'observed_top_right': observed_tr.tolist(),
        'inferred_top_right': observed_tr.tolist(),
        'horizontal_inset': round(inset, 2),
        'horizontal_inset_ratio': round(inset / board_width, 4),
    }
    if inset <= board_width * minimum_inset_ratio:
        return result
    dx = float(observed_tr[0] - tl[0])
    if abs(dx) < 1e-6:
        result['reason'] = 'top_edge_is_vertical'
        return result
    slope = float(observed_tr[1] - tl[1]) / dx
    target_x = float(br[0])
    target_y = float(tl[1]) + slope * (target_x - float(tl[0]))
    image_width, image_height = image_size
    if not (-0.05 * image_height <= target_y <= 1.05 * image_height and 0 <= target_x <= image_width):
        result['reason'] = 'inferred_corner_outside_image'
        return result
    repaired = ordered.copy()
    repaired[1] = [target_x, target_y]
    result.update({
        'applied': True,
        'reason': 'extended_straight_top_edge_to_right_pcb_edge',
        'inferred_top_right': [round(target_x, 2), round(target_y, 2)],
        'quad': np.rint(repaired).astype(int).tolist(),
    })
    return result

def normalize_board(image: np.ndarray, quad: list[list[float]]) -> tuple[np.ndarray, np.ndarray]:
    ordered = order_quad(np.asarray(quad, dtype=np.float32))
    width, height = quad_dimensions(ordered)
    if height > width:
        output_width, output_height = height, width
        destination = np.asarray([[0, output_height - 1], [0, 0], [output_width - 1, 0], [output_width - 1, output_height - 1]], dtype=np.float32)
    else:
        output_width, output_height = width, height
        destination = np.asarray([[0, 0], [output_width - 1, 0], [output_width - 1, output_height - 1], [0, output_height - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(ordered, destination)
    warped = cv2.warpPerspective(image, matrix, (output_width, output_height))
    return warped, matrix


def draw_corner_overlay(image: np.ndarray, quad: list[list[int]]) -> np.ndarray:
    overlay = image.copy()
    pts = np.asarray(quad, dtype=np.int32)
    cv2.polylines(overlay, [pts], True, (255, 0, 0), 5, cv2.LINE_AA)
    labels = ['TL', 'TR', 'BR', 'BL']
    for label, (x, y) in zip(labels, pts):
        cv2.circle(overlay, (int(x), int(y)), 8, (0, 0, 255), -1)
        cv2.putText(overlay, label, (int(x) + 10, int(y) - 10), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 255), 2, cv2.LINE_AA)
    return overlay


def main() -> int:
    parser = argparse.ArgumentParser(description='Detect motherboard corners and produce normalized 0-degree and 180-degree views')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    image = cv2.imread(str(args.image))
    if image is None:
        raise ValueError(f'cannot decode image: {args.image}')
    detection = detect_board_quad(image)
    normalized, matrix = normalize_board(image, detection['quad'])
    rotated = cv2.rotate(normalized, cv2.ROTATE_180)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    corner_path = args.output_dir / 'board-corners-overlay.jpg'
    normalized_path = args.output_dir / 'board-normalized-0.jpg'
    rotated_path = args.output_dir / 'board-normalized-180.jpg'
    cv2.imwrite(str(corner_path), draw_corner_overlay(image, detection['quad']))
    cv2.imwrite(str(normalized_path), normalized)
    cv2.imwrite(str(rotated_path), rotated)
    payload = {
        **detection,
        'image': str(args.image),
        'input_size': [image.shape[1], image.shape[0]],
        'normalized_size': [normalized.shape[1], normalized.shape[0]],
        'homography': matrix.tolist(),
        'corner_overlay': str(corner_path),
        'normalized_0': str(normalized_path),
        'normalized_180': str(rotated_path),
    }
    report = args.output_dir / 'board-normalization.json'
    report.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
