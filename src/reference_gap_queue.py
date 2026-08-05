#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_gap_queue(
    identifications: list[dict[str, Any]],
    verification: list[dict[str, Any]],
    cache_dir: Path,
) -> list[dict[str, Any]]:
    by_item = {str(row['item_id']): row for row in identifications}
    queue: list[dict[str, Any]] = []
    for result in verification:
        status = str(result.get('status') or '')
        if status not in {'no_reference', 'reference_conflict', 'reference_uncertain'}:
            continue
        item_id = str(result['item_id'])
        identification = by_item.get(item_id, {})
        board = identification.get('motherboard') or {}
        model = board.get('text') or result.get('model')
        if not model:
            continue
        listing_images = [str(path) for path in sorted(cache_dir.glob(f'{item_id}_*.jpg'))]
        queue.append({
            'item_id': item_id,
            'model': model,
            'identification_source': board.get('source'),
            'verification_status': status,
            'identity_score': float(result.get('identity_score') or 0.0),
            'listing_images': listing_images,
            'search_queries': [
                f'"{model}" motherboard official product image',
                f'"{model}" motherboard review high resolution',
                f'"{model}" motherboard ebay',
            ],
            'recommended_sources': ['manufacturer', 'review_site', 'ebay'],
            'next_action': 'collect_reference_candidates',
            'human_review_required': status in {'reference_conflict', 'reference_uncertain'},
        })
    return sorted(queue, key=lambda row: (not row['human_review_required'], row['model'], row['item_id']))


def candidate_manifest_from_verified_listings(queue: list[dict[str, Any]], approved_item_ids: set[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in queue:
        if row['item_id'] not in approved_item_ids:
            continue
        for image in row.get('listing_images', []):
            candidates.append({
                'model': row['model'],
                'source_type': 'shopgoodwill_verified',
                'source': image,
                'source_item_id': row['item_id'],
            })
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a queue for motherboard models missing or conflicting with reference data')
    parser.add_argument('--identifications', type=Path, required=True)
    parser.add_argument('--verification', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--approved-item-id', action='append', default=[])
    parser.add_argument('--candidate-output', type=Path)
    args = parser.parse_args()
    queue = build_gap_queue(
        json.loads(args.identifications.read_text(encoding='utf-8')),
        json.loads(args.verification.read_text(encoding='utf-8')),
        args.cache_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(queue, indent=2) + '\n', encoding='utf-8')
    candidate_count = 0
    if args.candidate_output:
        candidates = candidate_manifest_from_verified_listings(queue, set(args.approved_item_id))
        args.candidate_output.parent.mkdir(parents=True, exist_ok=True)
        args.candidate_output.write_text(json.dumps({'candidates': candidates}, indent=2) + '\n', encoding='utf-8')
        candidate_count = len(candidates)
    print(json.dumps({'queue_items': len(queue), 'candidate_images': candidate_count}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
