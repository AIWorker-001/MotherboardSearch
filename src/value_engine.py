#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


MONEY_RE = re.compile(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)")
SHIPPING_RE = re.compile(r"(?:shipping|ship)\s*[:$]?\s*\$?\s*([0-9]+(?:\.[0-9]{1,2})?)", re.I)


@dataclass
class ValueEstimate:
    item_id: str
    title: str
    current_bid: float
    shipping: float
    buyers_premium: float
    acquisition_cost: float
    gross_component_value: float
    repair_risk_cost: float
    expected_net_value: float
    expected_profit: float
    expected_roi: float | None
    recommended_max_bid: float
    confidence: float
    recommendation: str
    breakdown: dict[str, float]
    reasons: list[str]


def load_model(path: Path) -> dict[str, Any]:
    model = json.loads(path.read_text(encoding="utf-8"))
    if model.get("schema_version") != 1:
        raise ValueError("Unsupported value model schema")
    return model


def parse_money_fields(listing: dict[str, Any], default_shipping: float) -> tuple[float, float]:
    card = str(listing.get("card", ""))
    explicit_bid = listing.get("current_bid")
    explicit_shipping = listing.get("shipping")
    if explicit_bid is not None:
        current_bid = float(explicit_bid)
    else:
        matches = [float(value) for value in MONEY_RE.findall(card)]
        current_bid = matches[0] if matches else 0.0
    if explicit_shipping is not None:
        shipping = float(explicit_shipping)
    else:
        match = SHIPPING_RE.search(card)
        shipping = float(match.group(1)) if match else float(default_shipping)
    return current_bid, shipping


def chipset_bonus(title: str, model: dict[str, Any]) -> float:
    upper = title.upper()
    premium = model["chipset_patterns"].get("premium", [])
    return float(model["component_values"]["premium_chipset_bonus"]) if any(token in upper for token in premium) else 0.0


def confidence_from_result(result: dict[str, Any]) -> float:
    if result.get("cpu_confidence") is not None:
        base = float(result["cpu_confidence"])
    else:
        maxima = result.get("maxima", {})
        base = max((float(value) for value in maxima.values()), default=0.0)
    if result.get("needs_review"):
        base *= 0.75
    return max(0.0, min(1.0, base))


def estimate_item(listing: dict[str, Any], result: dict[str, Any], model: dict[str, Any]) -> ValueEstimate:
    assumptions = model["assumptions"]
    values = model["component_values"]
    risks = model["risk_costs"]
    current_bid, shipping = parse_money_fields(listing, assumptions["default_shipping"])
    buyers_premium = current_bid * float(assumptions["buyers_premium_rate"])
    acquisition_cost = current_bid + shipping + buyers_premium

    breakdown: dict[str, float] = {"motherboard": float(values["motherboard_base"])}
    reasons: list[str] = []
    cpu_state = result.get("cpu_state", "unclear")
    if cpu_state == "cooler_attached_cpu_highly_likely":
        breakdown["cpu"] = float(values["cpu_present_unknown"])
        breakdown["cooler_cpu_bonus"] = float(values["cooler_attached_cpu_bonus"])
        reasons.append("cooler_attached")
    elif cpu_state == "visible_cpu_likely":
        breakdown["cpu"] = float(values["cpu_present_unknown"])
        reasons.append("cpu_visible")
    elif cpu_state == "empty_socket_likely":
        reasons.append("empty_socket")
    elif cpu_state == "socket_cover_likely":
        reasons.append("socket_cover")

    maxima = result.get("maxima", {})
    if float(maxima.get("ram_dimm", maxima.get("ram", 0.0))) >= 0.38:
        breakdown["ram"] = float(values["ram_detected"])
    if float(maxima.get("nvme_ssd", maxima.get("nvme", 0.0))) >= 0.38:
        breakdown["nvme"] = float(values["nvme_detected"])
    bonus = chipset_bonus(str(listing.get("title", result.get("title", ""))), model)
    if bonus:
        breakdown["premium_chipset"] = bonus

    repair_risk = 0.0
    review_reasons = set(result.get("review_reasons", []))
    if cpu_state == "unclear":
        repair_risk += float(risks["unclear_cpu_state"])
    if "detector_disagreement" in review_reasons:
        repair_risk += float(risks["detector_disagreement"])
    if "possible_physical_damage" in review_reasons or float(result.get("damage_score", 0.0)) >= 0.38:
        repair_risk += float(risks["possible_physical_damage"])
    if cpu_state == "socket_cover_likely":
        repair_risk += float(risks["socket_cover"])

    gross = sum(breakdown.values())
    expected_net = max(0.0, gross - repair_risk)
    expected_profit = expected_net - acquisition_cost
    roi = (expected_profit / acquisition_cost) if acquisition_cost > 0 else None
    target_profit = float(assumptions["target_profit"])
    target_roi = float(assumptions["target_roi"])
    max_by_profit = expected_net - shipping - target_profit
    max_by_roi = ((expected_net - shipping) / (1.0 + target_roi)) if expected_net > shipping else 0.0
    recommended_max_bid = max(0.0, min(max_by_profit, max_by_roi))
    confidence = confidence_from_result(result)

    if confidence < float(assumptions["minimum_confidence_for_auto_bid"]):
        recommendation = "review"
    elif current_bid <= recommended_max_bid and expected_profit > 0:
        recommendation = "bid"
    else:
        recommendation = "pass"

    return ValueEstimate(
        item_id=str(listing["id"]),
        title=str(listing.get("title", result.get("title", ""))),
        current_bid=round(current_bid, 2),
        shipping=round(shipping, 2),
        buyers_premium=round(buyers_premium, 2),
        acquisition_cost=round(acquisition_cost, 2),
        gross_component_value=round(gross, 2),
        repair_risk_cost=round(repair_risk, 2),
        expected_net_value=round(expected_net, 2),
        expected_profit=round(expected_profit, 2),
        expected_roi=round(roi, 4) if roi is not None else None,
        recommended_max_bid=round(recommended_max_bid, 2),
        confidence=round(confidence, 4),
        recommendation=recommendation,
        breakdown={key: round(value, 2) for key, value in breakdown.items()},
        reasons=reasons + sorted(review_reasons),
    )


def rank_estimates(estimates: list[ValueEstimate]) -> list[ValueEstimate]:
    return sorted(
        estimates,
        key=lambda row: (
            1 if row.recommendation == "bid" else 0,
            row.expected_profit,
            row.confidence,
        ),
        reverse=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate AIWorker sourcing value and maximum bid")
    parser.add_argument("--listings", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=Path("config/value_model.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    model = load_model(args.model)
    listings = json.loads(args.listings.read_text(encoding="utf-8"))
    results = json.loads(args.results.read_text(encoding="utf-8"))
    result_by_id = {str(item["item_id"]): item for item in results}
    estimates = [estimate_item(item, result_by_id[str(item["id"])], model) for item in listings if str(item["id"]) in result_by_id]
    ranked = rank_estimates(estimates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps([asdict(row) for row in ranked], indent=2) + "\n", encoding="utf-8")
    for row in ranked:
        print(f"{row.item_id} | {row.recommendation} | profit=${row.expected_profit:.2f} | max_bid=${row.recommended_max_bid:.2f} | confidence={row.confidence:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
