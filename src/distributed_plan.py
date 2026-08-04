#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description='Create a portable distributed execution plan for AIWorkbench workers')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    tasks = []
    for shard in manifest['shards']:
        tasks.append({
            'run_id': args.run_id,
            'shard': shard['shard'],
            'items': shard['items'],
            'input': shard['path'],
            'output_dir': f"output/distributed/{args.run_id}/shard-{int(shard['shard']):03d}",
            'command': ['python3', 'src/process_shard.py', '--shard', shard['path'], '--output-dir', f"output/distributed/{args.run_id}/shard-{int(shard['shard']):03d}"],
        })
    plan = {'run_id': args.run_id, 'tasks': tasks, 'merge_output': f'output/distributed/{args.run_id}/merged_results.json'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'run_id': args.run_id, 'tasks': len(tasks)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
