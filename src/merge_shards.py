#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def merge_files(paths: list[Path]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for path in paths:
        for row in json.loads(path.read_text(encoding='utf-8')):
            item_id = str(row['item_id'])
            if item_id in merged:
                raise ValueError(f'duplicate item_id across shards: {item_id}')
            merged[item_id] = row
    return [merged[item_id] for item_id in sorted(merged)]


def main() -> int:
    parser = argparse.ArgumentParser(description='Merge distributed shard outputs into one detector report')
    parser.add_argument('--inputs', nargs='+', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = merge_files(args.inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'files': len(args.inputs), 'items': len(rows)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
