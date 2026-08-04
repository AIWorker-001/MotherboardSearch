#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def run_task(task: dict, root: Path) -> dict:
    command = [str(part) for part in task['command']]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    return {
        'shard': task['shard'],
        'returncode': completed.returncode,
        'stdout': completed.stdout,
        'stderr': completed.stderr,
        'result': str(Path(task['output_dir']) / 'results.json'),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Execute a distributed plan locally with bounded parallelism')
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(run_task, task, root): task for task in plan['tasks']}
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: int(row['shard']))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    failed = [row for row in results if row['returncode'] != 0]
    print(json.dumps({'tasks': len(results), 'failed': len(failed)}))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
