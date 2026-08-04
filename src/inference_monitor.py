#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    confidences = [float(row.get("cpu_confidence", 0.0)) for row in rows]
    reviews = [bool(row.get("needs_review")) for row in rows]
    classes = Counter(str(row.get("cpu_state", "unclear")) for row in rows)
    total = max(1, len(rows))
    return {
        "sample_count": len(rows),
        "mean_confidence": round(sum(confidences) / total, 4),
        "review_rate": round(sum(reviews) / total, 4),
        "class_frequencies": {label: round(count / total, 4) for label, count in sorted(classes.items())},
    }


def detect_drift(current: dict[str, Any], baseline: dict[str, Any], config: dict[str, Any]) -> list[str]:
    if baseline.get("sample_count", 0) <= 0:
        return []
    reasons = []
    if float(baseline.get("mean_confidence", 0.0)) - float(current["mean_confidence"]) > float(config["confidence_drop"]):
        reasons.append("confidence_drop")
    if float(current["review_rate"]) > float(config["review_rate_limit"]):
        reasons.append("review_rate")
    labels = set(current["class_frequencies"]) | set(baseline.get("class_frequencies", {}))
    if any(abs(float(current["class_frequencies"].get(label, 0.0)) - float(baseline.get("class_frequencies", {}).get(label, 0.0))) > float(config["class_frequency_delta"]) for label in labels):
        reasons.append("class_frequency_shift")
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor production detector confidence, review rate, and class drift")
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=Path("data/monitoring/baseline.json"))
    parser.add_argument("--deployment", type=Path, default=Path("config/deployment.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()
    rows = json.loads(args.results.read_text(encoding="utf-8"))
    deployment = json.loads(args.deployment.read_text(encoding="utf-8"))
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    current = summarize(rows)
    reasons = detect_drift(current, baseline, deployment["drift"])
    report = {"current": current, "baseline": baseline, "drift_detected": bool(reasons), "drift_reasons": reasons}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.update_baseline and current["sample_count"] >= int(deployment["minimum_images_for_drift"]):
        updated = {"schema_version": 1, "model": None, **current}
        args.baseline.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
