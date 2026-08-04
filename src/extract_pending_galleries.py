#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract embedded gallery records from pending candidates")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    galleries = []
    for candidate in candidates:
        gallery = dict(candidate.get("gallery", {}))
        gallery.setdefault("id", str(candidate["id"]))
        gallery.setdefault("title", candidate.get("title", ""))
        gallery.setdefault("urls", [])
        galleries.append(gallery)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(galleries, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"galleries": len(galleries)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
