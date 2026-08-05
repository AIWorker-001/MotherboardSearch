#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .motherboard_kb import add_reference, acquire_image, load_catalog, load_features, model_key, serialize_features
except ImportError:
    from motherboard_kb import add_reference, acquire_image, load_catalog, load_features, model_key, serialize_features

import cv2
import numpy as np


def candidate_id(model: str, source_type: str, source: str) -> str:
    return hashlib.sha256(f'{model_key(model)}|{source_type}|{source}'.encode()).hexdigest()[:16]


def load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    rows = payload.get('candidates', payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError('candidate manifest must be a list or contain candidates')
    return rows


def compare_feature_files(left: Path, right: Path, ratio_test: float = 0.75) -> dict[str, Any]:
    left_points, left_desc, _ = load_features(left)
    right_points, right_desc, _ = load_features(right)
    if len(left_desc) < 4 or len(right_desc) < 4:
        return {'good_matches': 0, 'inlier_ratio': 0.0, 'score': 0.0}
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(left_desc, right_desc, k=2)
    good = [a for a, b in pairs if a.distance < ratio_test * b.distance]
    inliers = 0
    if len(good) >= 4:
        src = np.float32([left_points[m.queryIdx] for m in good]).reshape(-1, 1, 2)
        dst = np.float32([right_points[m.trainIdx] for m in good]).reshape(-1, 1, 2)
        _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if mask is not None:
            inliers = int(mask.ravel().sum())
    ratio = inliers / max(1, len(good))
    score = min(1.0, len(good) / 60.0) * 0.45 + ratio * 0.55
    return {'good_matches': len(good), 'inlier_ratio': round(ratio, 4), 'score': round(score, 4)}


def prepare_candidates(config: dict[str, Any], manifest: list[dict[str, Any]], work_dir: Path) -> list[dict[str, Any]]:
    work_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in manifest:
        model = str(item['model'])
        source_type = str(item['source_type'])
        source = str(item['source'])
        identifier = candidate_id(model, source_type, source)
        image = work_dir / f'{identifier}.jpg'
        features = work_dir / f'{identifier}.npz'
        acquire_image(source, image)
        feature_info = serialize_features(image, features)
        rows.append({
            'id': identifier,
            'model': model,
            'model_key': model_key(model),
            'source_type': source_type,
            'source': source,
            'revision': item.get('revision'),
            'image': str(image),
            'feature_file': str(features),
            'keypoints': feature_info['keypoints'],
            'status': 'candidate',
        })
    return rows


def review_candidates(config: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matching = config.get('candidate_review', {})
    minimum_score = float(matching.get('minimum_pair_score', 0.52))
    minimum_agreeing = int(matching.get('minimum_agreeing_candidates', 2))
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        by_model.setdefault(row['model_key'], []).append(row)
    results = []
    for group in by_model.values():
        for row in group:
            agreements = []
            conflicts = []
            for other in group:
                if other['id'] == row['id']:
                    continue
                match = compare_feature_files(Path(row['feature_file']), Path(other['feature_file']), float(config['matching']['ratio_test']))
                entry = {'candidate_id': other['id'], **match}
                (agreements if match['score'] >= minimum_score else conflicts).append(entry)
            source_policy = config['sources'][row['source_type']]
            requires_manual = bool(source_policy.get('requires_manual_approval', False))
            if agreements and len(agreements) >= minimum_agreeing - 1 and not conflicts:
                recommendation = 'approve' if not requires_manual else 'manual_approval'
            elif agreements:
                recommendation = 'manual_review'
            else:
                recommendation = 'insufficient_evidence'
            results.append({**row, 'agreements': agreements, 'conflicts': conflicts, 'recommendation': recommendation})
    return results


def approve_candidates(config: dict[str, Any], catalog_path: Path, reviewed: list[dict[str, Any]], ids: set[str], approve_recommended: bool) -> list[dict[str, Any]]:
    selected = []
    for row in reviewed:
        should_approve = row['id'] in ids or (approve_recommended and row['recommendation'] == 'approve')
        if not should_approve:
            continue
        selected.append(add_reference(
            config,
            catalog_path,
            model=row['model'],
            source_type=row['source_type'],
            source=row['source'],
            approved=True,
            revision=row.get('revision'),
        ))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description='Prepare, compare, and approve motherboard reference candidates')
    parser.add_argument('--config', type=Path, default=Path('config/motherboard_kb.json'))
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--manifest', type=Path, required=True)
    prepare.add_argument('--work-dir', type=Path, default=Path('data/motherboard_kb/candidates'))
    prepare.add_argument('--output', type=Path, required=True)
    review = sub.add_parser('review')
    review.add_argument('--candidates', type=Path, required=True)
    review.add_argument('--output', type=Path, required=True)
    approve = sub.add_parser('approve')
    approve.add_argument('--reviewed', type=Path, required=True)
    approve.add_argument('--id', action='append', default=[])
    approve.add_argument('--approve-recommended', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.command == 'prepare':
        result = prepare_candidates(config, load_manifest(args.manifest), args.work_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    elif args.command == 'review':
        result = review_candidates(config, json.loads(args.candidates.read_text(encoding='utf-8')))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    else:
        result = approve_candidates(
            config,
            Path(config['catalog']),
            json.loads(args.reviewed.read_text(encoding='utf-8')),
            set(args.id),
            bool(args.approve_recommended),
        )
    print(json.dumps({'count': len(result), 'results': result}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
