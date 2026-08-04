#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from processing_state import detector_version

ROOT = Path(__file__).resolve().parents[1]
DETECTOR_FILES = [
    ROOT / "src" / "motherboard_search.py",
    ROOT / "src" / "collect_true_galleries.js",
]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the daily ShopGoodwill motherboard search incrementally")
    parser.add_argument("--query", default="motherboard")
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--retention-days", type=int, default=7)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--state", type=Path, default=ROOT / "data" / "processed.json")
    args = parser.parse_args()

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    listings = output / "listings.json"
    all_item_ids = output / "all_item_ids.txt"
    all_galleries = output / "all_galleries.json"
    candidates = output / "candidates.json"
    pending = output / "pending_listings.json"
    galleries = output / "pending_galleries.json"
    results = output / "new_worker_value_report.json"
    version = detector_version(DETECTOR_FILES)

    run(["node", "src/search_shopgoodwill.js", "--query", args.query, "--pages", str(args.pages), "--output", str(listings)])
    all_items = json.loads(listings.read_text(encoding="utf-8"))
    all_item_ids.write_text("\n".join(str(item["id"]) for item in all_items) + "\n", encoding="utf-8")
    run(["node", "src/collect_true_galleries.js", "--ids-file", str(all_item_ids), "--output", str(all_galleries)])
    run([
        sys.executable, "src/prepare_candidates.py",
        "--listings", str(listings), "--galleries", str(all_galleries), "--output", str(candidates),
    ])
    run([
        sys.executable, "src/processing_state.py", "pending",
        "--listings", str(candidates), "--state", str(args.state),
        "--version", version, "--output", str(pending),
        "--retention-days", str(args.retention_days),
    ])

    pending_items = json.loads(pending.read_text(encoding="utf-8"))
    if not pending_items:
        print(json.dumps({"status": "nothing_new", "detector_version": version, "processed": 0}))
        return 0

    run([
        sys.executable, "src/extract_pending_galleries.py",
        "--candidates", str(pending), "--output", str(galleries),
    ])
    run([
        sys.executable, "src/motherboard_search.py", "--galleries", str(galleries),
        "--output", str(results), "--cache-dir", str(output / "cache" / version),
    ])
    run([
        sys.executable, "src/processing_state.py", "merge",
        "--listings", str(pending), "--results", str(results),
        "--state", str(args.state), "--version", version,
        "--retention-days", str(args.retention_days),
    ])
    print(json.dumps({"status": "completed", "detector_version": version, "processed": len(pending_items), "state": str(args.state)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
