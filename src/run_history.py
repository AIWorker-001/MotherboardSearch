#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def load_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {'schema_version': 1, 'runs': []}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('schema_version') != 1:
        raise ValueError('Unsupported run history schema')
    payload.setdefault('runs', [])
    return payload


def append_run(history: dict[str, Any], report: dict[str, Any], *, source: str) -> None:
    history['runs'].append({
        'recorded_at': now_iso(),
        'source': source,
        'status': report.get('status'),
        'detector_version': report.get('detector_version'),
        'listings_found': report.get('listings_found', 0),
        'processed': report.get('processed', 0),
        'search_error_count': len(report.get('search_errors', [])),
        'gallery_error_count': len(report.get('gallery_errors', [])),
        'image_error_count': len(report.get('image_download_errors', [])),
        'rollback_recommended': bool(report.get('rollback_recommended')),
        'rollback_reasons': report.get('rollback_reasons', []),
    })


def prune(history: dict[str, Any], retention_days: int, *, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)
    before = len(history['runs'])
    history['runs'] = [row for row in history['runs'] if parse_time(row['recorded_at']) >= cutoff]
    return before - len(history['runs'])


def main() -> int:
    parser = argparse.ArgumentParser(description='Maintain compact daily run history')
    parser.add_argument('--history', type=Path, default=Path('data/runs/history.json'))
    parser.add_argument('--run-report', type=Path, required=True)
    parser.add_argument('--retention-days', type=int, default=30)
    args = parser.parse_args()
    history = load_history(args.history)
    report = json.loads(args.run_report.read_text(encoding='utf-8'))
    append_run(history, report, source=str(args.run_report))
    removed = prune(history, args.retention_days)
    args.history.parent.mkdir(parents=True, exist_ok=True)
    args.history.write_text(json.dumps(history, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'runs': len(history['runs']), 'pruned': removed}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
