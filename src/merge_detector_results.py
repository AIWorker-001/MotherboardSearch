#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def merge_item(legacy: dict[str, Any] | None, phase2: dict[str, Any] | None, mode: str) -> dict[str, Any]:
    if mode == "off":
        if legacy is None:
            raise ValueError("legacy result missing in off mode")
        return {**legacy, "detector_source": "legacy_clip"}
    if mode == "only":
        if phase2 is None:
            raise ValueError("phase2 result missing in only mode")
        return {**phase2, "detector_source": "phase2_spatial"}

    if phase2 is None and legacy is None:
        raise ValueError("both detector results missing")
    if phase2 is None:
        return {**legacy, "detector_source": "legacy_fallback", "needs_review": True, "review_reasons": ["phase2_missing"]}
    if legacy is None:
        return {**phase2, "detector_source": "phase2_only_available"}

    merged = dict(phase2)
    merged["legacy"] = {
        "cpu_state": legacy.get("cpu_state"),
        "value_score": legacy.get("value_score"),
        "maxima": legacy.get("maxima", {}),
    }
    merged["detector_source"] = "phase2_spatial_with_legacy_reference"
    if phase2.get("cpu_state") != legacy.get("cpu_state"):
        reasons = list(merged.get("review_reasons", []))
        if "detector_disagreement" not in reasons:
            reasons.append("detector_disagreement")
        merged["review_reasons"] = reasons
        merged["needs_review"] = True
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge legacy and spatial motherboard detector outputs")
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--phase2", type=Path, required=True)
    parser.add_argument("--mode", choices=("on", "off", "only"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    legacy = {str(item["item_id"]): item for item in read_json(args.legacy)}
    phase2 = {str(item["item_id"]): item for item in read_json(args.phase2)}
    item_ids = sorted(set(legacy) | set(phase2))
    merged = [merge_item(legacy.get(item_id), phase2.get(item_id), args.mode) for item_id in item_ids]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"items": len(merged), "mode": args.mode}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
