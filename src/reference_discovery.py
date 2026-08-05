#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

try:
    from .motherboard_kb import model_key
except ImportError:
    from motherboard_kb import model_key


def normalized_domain(url: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or '').lower().rstrip('.')
    return host[4:] if host.startswith('www.') else host


def domain_matches(domain: str, allowed: list[str]) -> bool:
    return any(domain == value or domain.endswith(f'.{value}') for value in allowed)


def source_type_for(page_url: str, config: dict[str, Any]) -> str | None:
    domain = normalized_domain(page_url)
    discovery = config.get('discovery', {})
    for source_type, domains in discovery.get('source_domains', {}).items():
        if domain_matches(domain, [str(value).lower() for value in domains]):
            return source_type
    marketplace_domains = [str(value).lower() for value in discovery.get('marketplace_domains', [])]
    if domain_matches(domain, marketplace_domains):
        return 'ebay'
    return None


def model_tokens(model: str) -> list[str]:
    ignored = {'MOTHERBOARD', 'MAINBOARD', 'BOARD', 'ATX', 'MATX', 'ITX'}
    return [token for token in re.findall(r'[A-Z0-9]+', model.upper()) if token not in ignored and len(token) >= 2]


def model_evidence(model: str, text: str) -> dict[str, Any]:
    haystack = set(re.findall(r'[A-Z0-9]+', text.upper()))
    tokens = model_tokens(model)
    matched = [token for token in tokens if token in haystack]
    ratio = len(matched) / max(1, len(tokens))
    return {'tokens': tokens, 'matched_tokens': matched, 'token_ratio': round(ratio, 4)}


def discovery_id(model: str, page_url: str, image_url: str) -> str:
    return hashlib.sha256(f'{model_key(model)}|{page_url}|{image_url}'.encode()).hexdigest()[:16]


def build_discovery_requests(gap_queue: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    maximum = int(config.get('discovery', {}).get('maximum_results_per_query', 8))
    requests = []
    for row in gap_queue:
        for query in row.get('search_queries', []):
            requests.append({
                'item_id': row['item_id'],
                'model': row['model'],
                'query': query,
                'maximum_results': maximum,
                'required_fields': ['page_url', 'image_url', 'title'],
            })
    return requests


def ingest_results(
    gap_queue: list[dict[str, Any]],
    results: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    models_by_item = {str(row['item_id']): str(row['model']) for row in gap_queue}
    minimum_ratio = float(config.get('discovery', {}).get('minimum_model_token_ratio', 0.60))
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for result in results:
        item_id = str(result.get('item_id') or '')
        model = str(result.get('model') or models_by_item.get(item_id) or '')
        page_url = str(result.get('page_url') or '')
        image_url = str(result.get('image_url') or '')
        title = str(result.get('title') or '')
        source_type = source_type_for(page_url, config)
        evidence = model_evidence(model, f'{title} {page_url} {image_url}') if model else {'token_ratio': 0.0, 'tokens': [], 'matched_tokens': []}
        reason = None
        if not model or not page_url or not image_url:
            reason = 'missing_required_fields'
        elif source_type is None:
            reason = 'unapproved_domain'
        elif evidence['token_ratio'] < minimum_ratio:
            reason = 'insufficient_model_evidence'
        elif not image_url.lower().startswith(('http://', 'https://')):
            reason = 'unsupported_image_url'
        dedupe_key = (model_key(model), image_url)
        if reason is None and dedupe_key in seen:
            reason = 'duplicate_image_url'
        row = {
            'id': discovery_id(model, page_url, image_url) if model and page_url and image_url else None,
            'item_id': item_id or None,
            'model': model or None,
            'source_type': source_type,
            'source': image_url or None,
            'page_url': page_url or None,
            'title': title,
            'model_evidence': evidence,
            'requires_manual_approval': bool(config.get('sources', {}).get(source_type or '', {}).get('requires_manual_approval', True)),
        }
        if reason:
            rejected.append({**row, 'rejection_reason': reason})
        else:
            seen.add(dedupe_key)
            accepted.append(row)
    return accepted, rejected


def main() -> int:
    parser = argparse.ArgumentParser(description='Create and validate source-discovery results for motherboard references')
    parser.add_argument('--config', type=Path, default=Path('config/motherboard_kb.json'))
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan')
    plan.add_argument('--gap-queue', type=Path, required=True)
    plan.add_argument('--output', type=Path, required=True)
    ingest = sub.add_parser('ingest')
    ingest.add_argument('--gap-queue', type=Path, required=True)
    ingest.add_argument('--results', type=Path, required=True)
    ingest.add_argument('--candidate-output', type=Path, required=True)
    ingest.add_argument('--rejected-output', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    gap_queue = json.loads(args.gap_queue.read_text(encoding='utf-8'))
    if args.command == 'plan':
        requests = build_discovery_requests(gap_queue, config)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'requests': requests}, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'requests': len(requests)}))
        return 0
    payload = json.loads(args.results.read_text(encoding='utf-8'))
    results = payload.get('results', payload) if isinstance(payload, dict) else payload
    accepted, rejected = ingest_results(gap_queue, results, config)
    args.candidate_output.parent.mkdir(parents=True, exist_ok=True)
    args.candidate_output.write_text(json.dumps({'candidates': accepted}, indent=2) + '\n', encoding='utf-8')
    args.rejected_output.parent.mkdir(parents=True, exist_ok=True)
    args.rejected_output.write_text(json.dumps({'rejected': rejected}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': len(accepted), 'rejected': len(rejected)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
