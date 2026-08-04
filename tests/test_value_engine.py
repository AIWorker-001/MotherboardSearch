from pathlib import Path

from src.value_engine import estimate_item, load_model, parse_money_fields, rank_estimates

MODEL = load_model(Path("config/value_model.json"))


def test_parse_bid_and_shipping_from_card():
    bid, shipping = parse_money_fields({"card": "Current Price $42.50 Shipping: $18.00"}, 99)
    assert bid == 42.50
    assert shipping == 18.00


def test_cooler_attached_can_produce_bid_recommendation():
    listing = {"id": "1", "title": "MSI Z390 motherboard", "card": "Current Price $20.00 Shipping: $15.00"}
    result = {"cpu_state": "cooler_attached_cpu_highly_likely", "cpu_confidence": 0.9, "maxima": {"ram_dimm": 0.5}, "review_reasons": []}
    estimate = estimate_item(listing, result, MODEL)
    assert estimate.recommendation == "bid"
    assert estimate.recommended_max_bid > estimate.current_bid
    assert estimate.expected_profit > 0


def test_damage_penalty_prevents_automatic_bid():
    listing = {"id": "2", "title": "ASUS Z790 board", "current_bid": 10, "shipping": 20}
    result = {"cpu_state": "visible_cpu_likely", "cpu_confidence": 0.9, "damage_score": 0.8, "review_reasons": ["possible_physical_damage"], "maxima": {}}
    estimate = estimate_item(listing, result, MODEL)
    assert estimate.repair_risk_cost >= 80
    assert estimate.recommendation != "bid"


def test_low_confidence_routes_to_review():
    listing = {"id": "3", "title": "B550 board", "current_bid": 10, "shipping": 10}
    result = {"cpu_state": "unclear", "cpu_confidence": 0.4, "review_reasons": [], "maxima": {}}
    estimate = estimate_item(listing, result, MODEL)
    assert estimate.recommendation == "review"


def test_ranking_prefers_bid_then_profit():
    first = estimate_item({"id": "1", "title": "Z390", "current_bid": 10, "shipping": 10}, {"cpu_state": "visible_cpu_likely", "cpu_confidence": 0.9, "maxima": {}, "review_reasons": []}, MODEL)
    second = estimate_item({"id": "2", "title": "H310", "current_bid": 60, "shipping": 10}, {"cpu_state": "unclear", "cpu_confidence": 0.5, "maxima": {}, "review_reasons": []}, MODEL)
    ranked = rank_estimates([second, first])
    assert ranked[0].item_id == "1"
