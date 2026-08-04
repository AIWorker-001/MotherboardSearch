#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def extract_metrics(result) -> dict:
    box = result.box
    return {
        "map50": float(box.map50),
        "map50_95": float(box.map),
        "precision": float(box.mp),
        "recall": float(box.mr),
    }


def promotion_decision(metrics: dict, thresholds: dict) -> tuple[bool, list[str]]:
    failures = []
    if metrics["map50"] < thresholds["minimum_map50"]:
        failures.append("map50")
    if metrics["precision"] < thresholds["minimum_precision"]:
        failures.append("precision")
    if metrics["recall"] < thresholds["minimum_recall"]:
        failures.append("recall")
    return not failures, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a trained detector and decide whether it is promotable")
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/training.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        from ultralytics import YOLO
    except ImportError as error:
        raise SystemExit("Install ultralytics with: python3 -m pip install ultralytics") from error
    thresholds = json.loads(args.config.read_text(encoding="utf-8"))["promotion"]
    result = YOLO(str(args.weights)).val(data=str(args.dataset), split="test")
    metrics = extract_metrics(result)
    promotable, failures = promotion_decision(metrics, thresholds)
    report = {"weights": str(args.weights), "metrics": metrics, "promotable": promotable, "failed_thresholds": failures}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
