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
    ROOT / "config" / "detection_fusion.json",
    ROOT / "src" / "detection_fusion.py",
    ROOT / "src" / "listing_context.py",
    ROOT / "config" / "listing_context.json",
    ROOT / "src" / "value_engine.py",
    ROOT / "config" / "value_model.json",
    ROOT / "src" / "model_identification.py",
    ROOT / "src" / "motherboard_kb.py",
    ROOT / "src" / "reference_verification.py",
    ROOT / "src" / "reference_regions.py",
    ROOT / "src" / "reference_regions.py",
    ROOT / "src" / "socket_region_detector.py",
    ROOT / "src" / "socket_first_detector.py",
    ROOT / "config" / "socket_first.json",
    ROOT / "src" / "reconcile_socket_results.py",
    ROOT / "config" / "socket_region_reconciliation.json",
    ROOT / "src" / "reference_gap_queue.py",
    ROOT / "src" / "reference_discovery.py",
    ROOT / "src" / "reference_candidates.py",
    ROOT / "src" / "knowledge_storage.py",
    ROOT / "config" / "motherboard_kb.json",
    ROOT / "src" / "market_pricing.py",
    ROOT / "src" / "phase4_enrichment.py",
    ROOT / "config" / "market_values.json",
    ROOT / "src" / "collect_true_galleries.js",
    ROOT / "src" / "production_detector.py",
    ROOT / "src" / "model_integrity.py",
    ROOT / "src" / "inference_monitor.py",
    ROOT / "config" / "deployment.json",
    ROOT / "src" / "operations_health.py",
    ROOT / "src" / "daily_report.py",
    ROOT / "config" / "operations.json",
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
    parser.add_argument("--production-model", choices=("auto", "fallback", "trained"), default=None)
    parser.add_argument("--distributed", choices=("off", "plan", "local"), default="off")
    parser.add_argument("--distributed-shards", type=int, default=None)
    parser.add_argument("--distributed-workers", type=int, default=2)
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
    production_results = output / "production_detector_report.json"
    monitoring_report = output / "inference_monitoring.json"
    annotated = output / "annotated"
    value_report = output / "value_report.json"
    identifications = output / "identifications.json"
    reference_verification = output / "reference_verification.json"
    reference_region_crops = output / "reference_regions"
    reference_region_crops = output / "reference_regions"
    socket_region_results = output / "socket_region_report.json"
    socket_region_annotated = output / "socket_region_annotated"
    reconciled_results = output / "reconciled_detector_report.json"
    reference_gap_queue = output / "reference_gap_queue.json"
    reference_discovery_plan = output / "reference_discovery_plan.json"
    market_pricing = output / "market_pricing.json"
    phase4_report = output / "phase4_value_report.json"
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

    distributed_used = False
    if args.distributed != "off":
        distributed_config = json.loads((ROOT / "config" / "distributed.json").read_text(encoding="utf-8"))
        shard_count = args.distributed_shards or int(distributed_config["default_shards"])
        if shard_count > int(distributed_config["maximum_shards"]):
            raise ValueError("distributed shard count exceeds configured maximum")
        run_id = f"daily-{version}"
        distributed_root = output / "distributed" / run_id
        inputs_dir = distributed_root / "inputs"
        plan_path = distributed_root / "plan.json"
        execution_path = distributed_root / "execution.json"
        run([sys.executable, "src/shard_work.py", "--items", str(pending), "--shards", str(shard_count), "--output-dir", str(inputs_dir)])
        run([sys.executable, "src/distributed_plan.py", "--manifest", str(inputs_dir / "manifest.json"), "--run-id", run_id, "--output", str(plan_path)])
        if args.distributed == "plan":
            print(json.dumps({"status": "distributed_plan_ready", "plan": str(plan_path), "run_id": run_id}))
            return 0
        run([sys.executable, "src/distributed_local_runner.py", "--plan", str(plan_path), "--workers", str(args.distributed_workers), "--output", str(execution_path)])
        execution = json.loads(execution_path.read_text(encoding="utf-8"))
        result_files = [row["result"] for row in execution if row["returncode"] == 0]
        run([sys.executable, "src/merge_shards.py", "--inputs", *result_files, "--output", str(results)])
        distributed_used = True
    else:
        run([
            sys.executable, "src/extract_pending_galleries.py",
            "--candidates", str(pending), "--output", str(galleries),
        ])
    if not distributed_used:
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

        run([
            sys.executable, "src/build_local_manifest.py", "--galleries", str(galleries),
            "--cache-dir", str(cache_dir), "--output", str(phase2_manifest),
        ])
        if args.phase2 != "off":
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
    deployment_path = ROOT / "config" / "deployment.json"
    if args.production_model:
        deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
        deployment["mode"] = args.production_model
        runtime_deployment = output / "deployment.runtime.json"
        runtime_deployment.write_text(json.dumps(deployment, indent=2) + "\n", encoding="utf-8")
    else:
        runtime_deployment = deployment_path
    run([
        sys.executable, "src/production_detector.py",
        "--manifest", str(phase2_manifest), "--deployment", str(runtime_deployment),
        "--fallback-results", str(results), "--output", str(production_results),
    ])
    run([
        sys.executable, "src/inference_monitor.py",
        "--results", str(production_results),
        "--baseline", str(ROOT / "data" / "monitoring" / "baseline.json"),
        "--deployment", str(runtime_deployment), "--output", str(monitoring_report),
    ])
    monitoring = json.loads(monitoring_report.read_text(encoding="utf-8"))
    rollback_recommended = bool(monitoring.get("drift_detected"))
    results = production_results
    run([
        sys.executable, "src/model_identification.py",
        "--listings", str(pending), "--cache-dir", str(cache_dir),
        "--catalog", str(ROOT / "config" / "market_values.json"),
        "--output", str(identifications),
    ])
    run([
        sys.executable, "src/reference_verification.py",
        "--identifications", str(identifications),
        "--cache-dir", str(cache_dir),
        "--config", str(ROOT / "config" / "motherboard_kb.json"),
        "--output", str(reference_verification),
        "--region-output-dir", str(reference_region_crops),
    ])
    run([
        sys.executable, "src/socket_region_detector.py",
        "--verification", str(reference_verification),
        "--config", str(ROOT / "config" / "detection_classes.json"),
        "--fusion-config", str(ROOT / "config" / "detection_fusion.json"),
        "--model", args.phase2_model,
        "--output", str(socket_region_results),
        "--annotated-dir", str(socket_region_annotated),
    ])
    run([
        sys.executable, "src/reconcile_socket_results.py",
        "--base-results", str(production_results),
        "--focused-results", str(socket_region_results),
        "--config", str(ROOT / "config" / "socket_region_reconciliation.json"),
        "--output", str(reconciled_results),
    ])
    results = reconciled_results
    run([
        sys.executable, "src/value_engine.py",
        "--listings", str(pending), "--results", str(results),
        "--model", str(ROOT / "config" / "value_model.json"),
        "--output", str(value_report),
    ])
    run([
        sys.executable, "src/reference_gap_queue.py",
        "--identifications", str(identifications),
        "--verification", str(reference_verification),
        "--cache-dir", str(cache_dir),
        "--output", str(reference_gap_queue),
    ])
    run([
        sys.executable, "src/reference_discovery.py", "plan",
        "--gap-queue", str(reference_gap_queue),
        "--config", str(ROOT / "config" / "motherboard_kb.json"),
        "--output", str(reference_discovery_plan),
    ])
    run([
        sys.executable, "src/market_pricing.py",
        "--identifications", str(identifications),
        "--catalog", str(ROOT / "config" / "market_values.json"),
        "--outcomes", str(ROOT / "data" / "purchase_outcomes.json"),
        "--output", str(market_pricing),
    ])
    run([
        sys.executable, "src/phase4_enrichment.py",
        "--value-report", str(value_report), "--identifications", str(identifications),
        "--pricing", str(market_pricing), "--output", str(phase4_report),
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
        "phase4_value_report": str(phase4_report) if phase4_report.exists() else None,
        "identifications": str(identifications) if identifications.exists() else None,
        "market_pricing": str(market_pricing) if market_pricing.exists() else None,
        "production_detector_report": str(production_results) if production_results.exists() else None,
        "reference_verification": str(reference_verification) if reference_verification.exists() else None,
        "reference_region_crops": str(reference_region_crops) if reference_region_crops.exists() else None,
        "socket_region_report": str(socket_region_results) if socket_region_results.exists() else None,
        "reconciled_detector_report": str(reconciled_results) if reconciled_results.exists() else None,
        "reference_gap_queue": str(reference_gap_queue) if reference_gap_queue.exists() else None,
        "reference_discovery_plan": str(reference_discovery_plan) if reference_discovery_plan.exists() else None,
        "inference_monitoring": str(monitoring_report) if monitoring_report.exists() else None,
        "rollback_recommended": rollback_recommended,
        "rollback_reasons": monitoring.get("drift_reasons", []),
        "state": str(args.state),
        "distributed": distributed_used,
    }
    run_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    run([
        sys.executable, "src/phase8_finalize.py",
        "--output-dir", str(output),
        "--config", str(ROOT / "config" / "operations.json"),
    ])
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
