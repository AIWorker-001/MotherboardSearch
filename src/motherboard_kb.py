#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .knowledge_storage import KnowledgeStorage
except ImportError:
    from knowledge_storage import KnowledgeStorage

import cv2
import numpy as np


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def model_key(value: str) -> str:
    return re.sub(r'[^A-Z0-9]+', '-', value.upper()).strip('-')


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_catalog(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {'schema_version': 1, 'boards': {}}
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload.setdefault('boards', {})
    return payload


def save_catalog(path: Path, catalog: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')


def read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'cannot decode image: {path}')
    return image


def extract_features(path: Path) -> tuple[list[cv2.KeyPoint], np.ndarray | None, tuple[int, int]]:
    image = read_image(path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=3500, scaleFactor=1.2, nlevels=8)
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    return keypoints, descriptors, (image.shape[1], image.shape[0])


def serialize_features(image_path: Path, output: Path) -> dict[str, Any]:
    keypoints, descriptors, size = extract_features(image_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        points=np.asarray([kp.pt for kp in keypoints], dtype=np.float32),
        descriptors=descriptors if descriptors is not None else np.empty((0, 32), dtype=np.uint8),
        size=np.asarray(size, dtype=np.int32),
    )
    return {'keypoints': len(keypoints), 'size': list(size), 'feature_file': str(output)}


def acquire_image(source: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if re.match(r'^https?://', source):
        request = urllib.request.Request(source, headers={'User-Agent': 'MotherboardSearch/1.0'})
        with urllib.request.urlopen(request, timeout=45) as response, destination.open('wb') as stream:
            shutil.copyfileobj(response, stream)
    else:
        shutil.copy2(Path(source), destination)
    read_image(destination)


def add_reference(
    config: dict[str, Any], catalog_path: Path, *, model: str, source_type: str,
    source: str, approved: bool, revision: str | None = None,
) -> dict[str, Any]:
    source_policy = config['sources'][source_type]
    if source_policy.get('requires_manual_approval') and not approved:
        raise ValueError(f'{source_type} references require --approved')
    catalog = load_catalog(catalog_path)
    key = model_key(model)
    board = catalog['boards'].setdefault(key, {
        'model': model, 'aliases': [], 'socket': None, 'regions': {}, 'references': [],
    })
    reference_id = hashlib.sha256(f'{key}|{source_type}|{source}'.encode()).hexdigest()[:16]
    image_path = Path(config['reference_root']) / key / f'{reference_id}.jpg'
    feature_path = Path(config['feature_root']) / key / f'{reference_id}.npz'
    acquire_image(source, image_path)
    features = serialize_features(image_path, feature_path)
    storage = KnowledgeStorage(config.get('storage', {'backend': 'local'}))
    common_metadata = {
        'model': model,
        'model_key': key,
        'reference_id': reference_id,
        'source_type': source_type,
        'revision': revision,
    }
    image_object = storage.put(image_path, metadata={**common_metadata, 'kind': 'reference_image'}, content_type='image/jpeg')
    feature_object = storage.put(feature_path, metadata={**common_metadata, 'kind': 'orb_features'}, content_type='application/x-npz')
    record = {
        'id': reference_id, 'source_type': source_type, 'source': source,
        'trust': float(source_policy['trust']), 'approved': approved or not source_policy.get('requires_manual_approval'),
        'revision': revision, 'image': str(image_path), 'sha256': sha256(image_path),
        'feature_file': str(feature_path), 'image_object': image_object, 'feature_object': feature_object,
        'keypoints': features['keypoints'], 'size': features['size'], 'added_at': now_iso(),
    }
    board['references'] = [row for row in board['references'] if row['id'] != reference_id] + [record]
    save_catalog(catalog_path, catalog)
    return record


def load_features(path: Path) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    data = np.load(path)
    return data['points'], data['descriptors'], tuple(int(v) for v in data['size'])


def match_reference(query_path: Path, reference: dict[str, Any], ratio_test: float, storage: KnowledgeStorage | None = None) -> dict[str, Any]:
    query_kp, query_desc, query_size = extract_features(query_path)
    if reference.get('feature_object'):
        storage = storage or KnowledgeStorage({'backend': 'local'})
        feature_path = storage.materialize(reference['feature_object'], suffix='.npz')
    else:
        feature_path = Path(reference['feature_file'])
    ref_points, ref_desc, ref_size = load_features(feature_path)
    if query_desc is None or len(query_desc) < 4 or len(ref_desc) < 4:
        return {'score': 0.0, 'good_matches': 0, 'inlier_ratio': 0.0, 'homography': None}
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(ref_desc, query_desc, k=2)
    good = [a for a, b in pairs if a.distance < ratio_test * b.distance]
    homography = None
    inliers = 0
    if len(good) >= 4:
        src = np.float32([ref_points[m.queryIdx] for m in good]).reshape(-1, 1, 2)
        dst = np.float32([query_kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if matrix is not None and mask is not None:
            homography = matrix.tolist()
            inliers = int(mask.ravel().sum())
    inlier_ratio = inliers / max(1, len(good))
    match_strength = min(1.0, len(good) / 60.0)
    score = match_strength * 0.45 + inlier_ratio * 0.55
    return {
        'score': round(score * float(reference.get('trust', 1.0)), 4),
        'raw_score': round(score, 4), 'good_matches': len(good),
        'inliers': inliers, 'inlier_ratio': round(inlier_ratio, 4),
        'homography': homography, 'reference_size': list(ref_size), 'query_size': list(query_size),
    }


def verify_model(config: dict[str, Any], catalog: dict[str, Any], model: str, images: list[Path]) -> dict[str, Any]:
    key = model_key(model)
    board = catalog.get('boards', {}).get(key)
    if not board or not board.get('references'):
        return {'model': model, 'status': 'no_reference', 'identity_score': 0.0, 'best_match': None}
    results = []
    storage = KnowledgeStorage(config.get('storage', {'backend': 'local'}))
    for image in images:
        for reference in board['references'][: int(config['matching']['maximum_references_per_model'])]:
            if not reference.get('approved', False):
                continue
            match = match_reference(image, reference, float(config['matching']['ratio_test']), storage)
            results.append({'listing_image': str(image), 'reference_id': reference['id'], 'source_type': reference['source_type'], **match})
    best = max(results, key=lambda row: row['score'], default=None)
    score = float(best['score']) if best else 0.0
    if best and best['good_matches'] >= int(config['matching']['minimum_good_matches']) and best['inlier_ratio'] >= float(config['matching']['minimum_inlier_ratio']) and score >= float(config['matching']['minimum_identity_score']):
        status = 'reference_confirmed'
    elif score < float(config['matching']['conflict_score']):
        status = 'reference_conflict'
    else:
        status = 'reference_uncertain'
    return {'model': model, 'status': status, 'identity_score': round(score, 4), 'best_match': best, 'matches_evaluated': len(results)}


def project_region(region: list[list[float]], homography: list[list[float]]) -> list[list[float]]:
    points = np.asarray(region, dtype=np.float32).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(points, np.asarray(homography, dtype=np.float64))
    return [[round(float(x), 2), round(float(y), 2)] for x, y in projected.reshape(-1, 2)]


def main() -> int:
    parser = argparse.ArgumentParser(description='Manage and query the Motherboard Knowledge Base')
    parser.add_argument('--config', type=Path, default=Path('config/motherboard_kb.json'))
    sub = parser.add_subparsers(dest='command', required=True)
    add = sub.add_parser('add-reference')
    add.add_argument('--model', required=True); add.add_argument('--source-type', required=True)
    add.add_argument('--source', required=True); add.add_argument('--approved', action='store_true'); add.add_argument('--revision')
    verify = sub.add_parser('verify')
    verify.add_argument('--model', required=True); verify.add_argument('--images', nargs='+', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    catalog_path = Path(config['catalog'])
    if args.command == 'add-reference':
        result = add_reference(config, catalog_path, model=args.model, source_type=args.source_type, source=args.source, approved=args.approved, revision=args.revision)
    else:
        result = verify_model(config, load_catalog(catalog_path), args.model, args.images)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
