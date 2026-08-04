#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def stable_shard(item_id: str, shard_count: int) -> int:
    digest = hashlib.sha256(item_id.encode('utf-8')).digest()
    return int.from_bytes(digest[:8], 'big') % shard_count


def split_items(items: list[dict[str, Any]], shard_count: int) -> list[list[dict[str, Any]]]:
    shards = [[] for _ in range(shard_count)]
    for item in items:
        shards[stable_shard(str(item['id']), shard_count)].append(item)
    return shards


def main() -> int:
    parser = argparse.ArgumentParser(description='Split pending motherboard listings into deterministic worker shards')
    parser.add_argument('--items', type=Path, required=True)
    parser.add_argument('--shards', type=int, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.shards < 1:
        raise ValueError('shards must be positive')
    items = json.loads(args.items.read_text(encoding='utf-8'))
    shards = split_items(items, args.shards)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, rows in enumerate(shards):
        path = args.output_dir / f'shard-{index:03d}.json'
        path.write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
        manifest.append({'shard': index, 'path': str(path), 'items': len(rows), 'item_ids': [str(row['id']) for row in rows]})
    (args.output_dir / 'manifest.json').write_text(json.dumps({'shard_count': args.shards, 'total_items': len(items), 'shards': manifest}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'shard_count': args.shards, 'total_items': len(items), 'sizes': [len(rows) for rows in shards]}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
