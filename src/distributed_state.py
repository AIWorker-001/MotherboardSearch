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


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {'schema_version': 1, 'runs': []}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('schema_version') != 1:
        raise ValueError('Unsupported distributed state schema')
    payload.setdefault('runs', [])
    return payload


def find_run(state: dict[str, Any], run_id: str) -> dict[str, Any]:
    run = next((row for row in state['runs'] if row['run_id'] == run_id), None)
    if run is None:
        raise ValueError(f'Unknown run_id: {run_id}')
    return run


def initialize_run(state: dict[str, Any], run_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    state['runs'] = [row for row in state['runs'] if row['run_id'] != run_id]
    run = {
        'run_id': run_id,
        'created_at': now_iso(),
        'updated_at': now_iso(),
        'status': 'pending',
        'shards': [
            {'shard': row['shard'], 'items': row['items'], 'status': 'pending', 'worker_id': None, 'attempts': 0, 'result': None, 'error': None, 'updated_at': now_iso()}
            for row in manifest['shards']
        ],
    }
    state['runs'].append(run)
    return run


def claim_shard(run: dict[str, Any], worker_id: str) -> dict[str, Any] | None:
    shard = next((row for row in run['shards'] if row['status'] in {'pending', 'retry'}), None)
    if shard is None:
        return None
    shard.update({'status': 'running', 'worker_id': worker_id, 'attempts': int(shard.get('attempts', 0)) + 1, 'updated_at': now_iso(), 'error': None})
    run['status'] = 'running'
    run['updated_at'] = now_iso()
    return shard


def complete_shard(run: dict[str, Any], shard_id: int, result: str) -> None:
    shard = next(row for row in run['shards'] if int(row['shard']) == shard_id)
    shard.update({'status': 'completed', 'result': result, 'updated_at': now_iso(), 'error': None})
    run['updated_at'] = now_iso()
    if all(row['status'] == 'completed' for row in run['shards']):
        run['status'] = 'completed'


def fail_shard(run: dict[str, Any], shard_id: int, error: str, retry_limit: int) -> None:
    shard = next(row for row in run['shards'] if int(row['shard']) == shard_id)
    status = 'retry' if int(shard.get('attempts', 0)) <= retry_limit else 'failed'
    shard.update({'status': status, 'error': error, 'updated_at': now_iso()})
    run['status'] = 'failed' if status == 'failed' else 'running'
    run['updated_at'] = now_iso()


def recover_stale(run: dict[str, Any], stale_minutes: int, *, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    recovered = 0
    for shard in run['shards']:
        if shard['status'] == 'running' and now - parse_time(shard['updated_at']) > timedelta(minutes=stale_minutes):
            shard.update({'status': 'retry', 'worker_id': None, 'error': 'stale_assignment', 'updated_at': now_iso()})
            recovered += 1
    if recovered:
        run['updated_at'] = now_iso()
    return recovered


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Manage distributed MotherboardSearch shard state')
    parser.add_argument('--state', type=Path, default=Path('data/distributed/state.json'))
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('--run-id', required=True)
    init.add_argument('--manifest', type=Path, required=True)
    claim = sub.add_parser('claim')
    claim.add_argument('--run-id', required=True)
    claim.add_argument('--worker-id', required=True)
    complete = sub.add_parser('complete')
    complete.add_argument('--run-id', required=True)
    complete.add_argument('--shard', type=int, required=True)
    complete.add_argument('--result', required=True)
    fail = sub.add_parser('fail')
    fail.add_argument('--run-id', required=True)
    fail.add_argument('--shard', type=int, required=True)
    fail.add_argument('--error', required=True)
    fail.add_argument('--retry-limit', type=int, default=2)
    recover = sub.add_parser('recover')
    recover.add_argument('--run-id', required=True)
    recover.add_argument('--stale-minutes', type=int, default=60)
    args = parser.parse_args()
    state = load_state(args.state)
    if args.command == 'init':
        run = initialize_run(state, args.run_id, json.loads(args.manifest.read_text(encoding='utf-8')))
        result = {'run_id': run['run_id'], 'shards': len(run['shards'])}
    else:
        run = find_run(state, args.run_id)
        if args.command == 'claim':
            shard = claim_shard(run, args.worker_id)
            result = shard or {'status': 'none_available'}
        elif args.command == 'complete':
            complete_shard(run, args.shard, args.result)
            result = {'status': 'completed', 'shard': args.shard}
        elif args.command == 'fail':
            fail_shard(run, args.shard, args.error, args.retry_limit)
            result = {'status': next(row['status'] for row in run['shards'] if row['shard'] == args.shard), 'shard': args.shard}
        else:
            result = {'recovered': recover_stale(run, args.stale_minutes)}
    save_state(args.state, state)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
