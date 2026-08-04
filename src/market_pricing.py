#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PriceRange:
    median: float
    low: float
    high: float
    samples: int
    source: str


def load_catalog(path: Path) -> dict[str, Any]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1:
        raise ValueError("Unsupported market catalog schema")
    return catalog


def load_outcomes(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("outcomes", []))


def empirical_range(values: list[float]) -> PriceRange | None:
    if not values:
        return None
    ordered = sorted(values)
    median = statistics.median(ordered)
    low = ordered[max(0, int(len(ordered) * 0.2) - 1)]
    high = ordered[min(len(ordered) - 1, int(len(ordered) * 0.8))]
    return PriceRange(round(median, 2), round(low, 2), round(high, 2), len(values), "purchase_outcomes")


def lookup(component_type: str, model_name: str | None, catalog: dict[str, Any], outcomes: list[dict[str, Any]]) -> PriceRange:
    relevant = [
        float(row["realized_value"])
        for row in outcomes
        if row.get("component_type") == component_type and row.get("model") == model_name and row.get("realized_value") is not None
    ]
    empirical = empirical_range(relevant)
    if empirical and empirical.samples >= 3:
        return empirical
    section = "motherboards" if component_type == "motherboard" else "cpus" if component_type == "cpu" else None
    if section and model_name and model_name in catalog.get(section, {}):
        row = catalog[section][model_name]
        return PriceRange(float(row["median"]), float(row["low"]), float(row["high"]), int(row.get("samples", 0)), "catalog")
    row = catalog["defaults"][component_type]
    return PriceRange(float(row["median"]), float(row["low"]), float(row["high"]), int(row.get("samples", 0)), "default")


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve market price ranges for identified hardware")
    parser.add_argument("--identifications", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("config/market_values.json"))
    parser.add_argument("--outcomes", type=Path, default=Path("data/purchase_outcomes.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    identifications = json.loads(args.identifications.read_text(encoding="utf-8"))
    catalog = load_catalog(args.catalog)
    outcomes = load_outcomes(args.outcomes)
    result = []
    for row in identifications:
        board_name = row.get("motherboard", {}).get("text") if row.get("motherboard") else None
        cpu_name = row.get("cpu", {}).get("text") if row.get("cpu") else None
        board = lookup("motherboard", board_name, catalog, outcomes)
        cpu = lookup("cpu", cpu_name, catalog, outcomes)
        result.append({
            "item_id": row["item_id"],
            "motherboard_model": board_name,
            "cpu_model": cpu_name,
            "motherboard_price": board.__dict__,
            "cpu_price": cpu.__dict__,
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
