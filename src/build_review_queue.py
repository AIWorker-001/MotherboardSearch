#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def score_candidate(row: dict[str, Any], weights: dict[str, float]) -> float:
    confidence = float(row.get("cpu_confidence", row.get("confidence", 0.0)))
    uncertainty = 1.0 - max(0.0, min(1.0, confidence))
    reasons = set(row.get("review_reasons", []))
    disagreement = 1.0 if "detector_disagreement" in reasons else 0.0
    novelty = 1.0 if not row.get("identification", {}).get("motherboard") else 0.0
    return (
        uncertainty * weights["uncertainty_weight"]
        + disagreement * weights["disagreement_weight"]
        + novelty * weights["novelty_weight"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Select uncertain and novel listings for human labeling")
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/training.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.results.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))["active_learning"]
    ranked = sorted(rows, key=lambda row: score_candidate(row, config), reverse=True)
    queue = []
    for row in ranked[: int(config["review_limit"])]:
        queue.append({
            "item_id": row["item_id"],
            "title": row.get("title", ""),
            "priority": round(score_candidate(row, config), 4),
            "review_reasons": row.get("review_reasons", []),
            "images": row.get("images", []),
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"queued": len(queue)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
