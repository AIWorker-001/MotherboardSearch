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
    ROOT / "src" / "object_detector.py",
    ROOT / "src" / "phase2_detector.py",
    ROOT / "config" / "detection_classes.json",
    ROOT / "src" / "value_engine.py",
    ROOT / "config" / "value_model.json",
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
    parser.add_argument("--browser-retries", type=int, default=4)
    parser.add_argument("--gallery-concurrency", type=int, default=4)
    parser.add_argument("--download-workers", type=int, default=8)
    parser.add_argument("--phase2", choices=("on", "off", "only"), default="on")
    parser.add_argument("--phase2-model", default="IDEA-Research/grounding-dino-tiny")
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
    legacy_results = output / "legacy_worker_value_report.json"
    phase2_manifest = output / "phase2_manifest.json"
    phase2_results = output / "phase2_report.json"
    results = output / "new_worker_value_report.json"
    annotated = output / "annotated"
    value_report = output / "value_report.json"
    search_errors = output / "search_errors.json"
    gallery_errors = output / "gallery_errors.json"
    image_errors = output / "image_download_errors.json"
    session = output / "session" / "shopgoodwill.json"
    run_report = output / "run_report.json"
    version = detector_version(DETECTOR_FILES)

    run([
        "node", "src/search_shopgoodwill.js", "--query", args.query, "--pages", str(args.pages),
        "--output", str(listings), "--errors", str(search_errors), "--session", str(session),
        "--retries", str(args.browser_retries),
    ])
    all_items = json.loads(listings.read_text(encoding="utf-8"))
    all_item_ids.write_text("\n".join(str(item["id"]) for item in all_items) + "\n", encoding="utf-8")
    run([
        "node", "src/collect_true_galleries.js", "--ids-file", str(all_item_ids),
        "--output", str(all_galleries), "--errors", str(gallery_errors), "--session", str(session),
        "--retries", str(args.browser_retries), "--concurrency", str(args.gallery_concurrency),
    ])
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
    cache_dir = output / "cache" / version
    if args.phase2 != "only":
        run([
            sys.executable, "src/motherboard_search.py", "--galleries", str(galleries),
            "--output", str(legacy_results), "--cache-dir", str(cache_dir),
            "--errors", str(image_errors), "--download-workers", str(args.download_workers),
        ])
    else:
        run([
            sys.executable, "src/download_gallery_images.py", "--galleries", str(galleries),
            "--cache-dir", str(cache_dir), "--errors", str(image_errors),
            "--download-workers", str(args.download_workers),
        ])

    if args.phase2 != "off":
        run([
            sys.executable, "src/build_local_manifest.py", "--galleries", str(galleries),
            "--cache-dir", str(cache_dir), "--output", str(phase2_manifest),
        ])
        run([
            sys.executable, "src/phase2_detector.py", "--manifest", str(phase2_manifest),
            "--model", args.phase2_model, "--output", str(phase2_results),
            "--annotated-dir", str(annotated),
        ])

    run([
        sys.executable, "src/merge_detector_results.py",
        "--legacy", str(legacy_results), "--phase2", str(phase2_results),
        "--mode", args.phase2, "--output", str(results),
    ])
    run([
        sys.executable, "src/value_engine.py",
        "--listings", str(pending), "--results", str(results),
        "--model", str(ROOT / "config" / "value_model.json"),
        "--output", str(value_report),
    ])
    run([
        sys.executable, "src/processing_state.py", "merge",
        "--listings", str(pending), "--results", str(results),
        "--state", str(args.state), "--version", version,
        "--retention-days", str(args.retention_days),
    ])
    def read_errors(path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return [{"error": "invalid_error_report", "path": str(path)}]

    report = {
        "status": "completed",
        "detector_version": version,
        "listings_found": len(all_items),
        "processed": len(pending_items),
        "search_errors": read_errors(search_errors),
        "gallery_errors": read_errors(gallery_errors),
        "image_download_errors": read_errors(image_errors),
        "phase2_mode": args.phase2,
        "phase2_model": args.phase2_model if args.phase2 != "off" else None,
        "phase2_report": str(phase2_results) if phase2_results.exists() else None,
        "annotated_dir": str(annotated) if annotated.exists() else None,
        "value_report": str(value_report) if value_report.exists() else None,
        "state": str(args.state),
    }
    run_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
