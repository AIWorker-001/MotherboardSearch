#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def evaluate_health(run_report: dict[str, Any], production_results: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    listings = max(1, int(run_report.get('listings_found', 0)))
    processed = max(1, int(run_report.get('processed', 0)))
    search_errors = len(run_report.get('search_errors', []))
    gallery_errors = len(run_report.get('gallery_errors', []))
    image_errors = len(run_report.get('image_download_errors', []))
    review_rate = sum(bool(row.get('needs_review')) for row in production_results) / max(1, len(production_results))
    gallery_error_rate = gallery_errors / listings
    image_error_rate = image_errors / processed

    if search_errors > int(config['maximum_search_errors']):
        reasons.append('search_errors')
    if gallery_error_rate > float(config['maximum_gallery_error_rate']):
        reasons.append('gallery_error_rate')
    if image_error_rate > float(config['maximum_image_error_rate']):
        reasons.append('image_error_rate')
    if review_rate > float(config['maximum_review_rate']):
        reasons.append('review_rate')
    if run_report.get('rollback_recommended'):
        reasons.append('model_drift')

    return {
        'healthy': not reasons,
        'reasons': reasons,
        'metrics': {
            'search_errors': search_errors,
            'gallery_error_rate': round(gallery_error_rate, 4),
            'image_error_rate': round(image_error_rate, 4),
            'review_rate': round(review_rate, 4),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Evaluate operational health of a daily run')
    parser.add_argument('--run-report', type=Path, required=True)
    parser.add_argument('--production-results', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('config/operations.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run_report = json.loads(args.run_report.read_text(encoding='utf-8'))
    results = json.loads(args.production_results.read_text(encoding='utf-8'))
    config = json.loads(args.config.read_text(encoding='utf-8'))['health']
    health = evaluate_health(run_report, results, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(health, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(health))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
