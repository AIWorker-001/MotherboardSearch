#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a phase-2 detector manifest from cached listing images")
    parser.add_argument("--galleries", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    galleries = json.loads(args.galleries.read_text(encoding="utf-8"))
    manifest = []
    for item in galleries:
        item_id = str(item["id"])
        images = sorted(str(path) for path in args.cache_dir.glob(f"{item_id}_*.jpg"))
        manifest.append({"id": item_id, "title": item.get("title", ""), "images": images})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"items": len(manifest), "images": sum(len(item["images"]) for item in manifest)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
