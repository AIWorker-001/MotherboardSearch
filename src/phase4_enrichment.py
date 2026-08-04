#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich value estimates with model-specific market ranges")
    parser.add_argument("--value-report", type=Path, required=True)
    parser.add_argument("--identifications", type=Path, required=True)
    parser.add_argument("--pricing", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = json.loads(args.value_report.read_text(encoding="utf-8"))
    identifications = {row["item_id"]: row for row in json.loads(args.identifications.read_text(encoding="utf-8"))}
    pricing = {row["item_id"]: row for row in json.loads(args.pricing.read_text(encoding="utf-8"))}
    enriched = []
    for row in values:
        item_id = row["item_id"]
        identification = identifications.get(item_id, {})
        price = pricing.get(item_id, {})
        board = price.get("motherboard_price", {})
        cpu = price.get("cpu_price", {})
        low = float(board.get("low", 0)) + (float(cpu.get("low", 0)) if row.get("reasons") and any(r in row["reasons"] for r in ("cpu_visible", "cooler_attached")) else 0)
        high = float(board.get("high", 0)) + (float(cpu.get("high", 0)) if row.get("reasons") and any(r in row["reasons"] for r in ("cpu_visible", "cooler_attached")) else 0)
        median = float(board.get("median", 0)) + (float(cpu.get("median", 0)) if row.get("reasons") and any(r in row["reasons"] for r in ("cpu_visible", "cooler_attached")) else 0)
        acquisition = float(row.get("acquisition_cost", 0))
        row["identification"] = identification
        row["market_pricing"] = price
        row["market_value_interval"] = {"low": round(low, 2), "median": round(median, 2), "high": round(high, 2)}
        row["profit_interval"] = {
            "low": round(low - acquisition, 2),
            "median": round(median - acquisition, 2),
            "high": round(high - acquisition, 2),
        }
        row["recommended_max_bid_interval"] = {
            "conservative": round(max(0.0, low - float(row.get("shipping", 0)) - 60.0), 2),
            "expected": round(max(0.0, median - float(row.get("shipping", 0)) - 60.0), 2),
            "optimistic": round(max(0.0, high - float(row.get("shipping", 0)) - 60.0), 2),
        }
        enriched.append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(enriched, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
