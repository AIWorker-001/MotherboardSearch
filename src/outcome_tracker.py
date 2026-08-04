#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Record actual purchase and resale outcomes")
    parser.add_argument("--file", type=Path, default=Path("data/purchase_outcomes.json"))
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--component-type", choices=("motherboard", "cpu", "ram", "nvme"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--purchase-cost", type=float, required=True)
    parser.add_argument("--realized-value", type=float, required=True)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    payload = {"schema_version": 1, "outcomes": []}
    if args.file.exists():
        payload = json.loads(args.file.read_text(encoding="utf-8"))
    payload.setdefault("outcomes", []).append({
        "item_id": args.item_id,
        "component_type": args.component_type,
        "model": args.model,
        "purchase_cost": args.purchase_cost,
        "realized_value": args.realized_value,
        "notes": args.notes,
        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    })
    args.file.parent.mkdir(parents=True, exist_ok=True)
    args.file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"outcomes": len(payload["outcomes"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
