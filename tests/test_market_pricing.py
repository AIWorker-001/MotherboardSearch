from src.market_pricing import empirical_range, lookup


def test_empirical_range():
    result = empirical_range([80, 90, 100, 110, 120])
    assert result.median == 100
    assert result.samples == 5


def test_outcomes_override_catalog_after_three_samples():
    catalog = {"cpus": {"CPU X": {"median": 50, "low": 40, "high": 60, "samples": 10}}, "defaults": {"cpu": {"median": 10, "low": 5, "high": 15, "samples": 0}}}
    outcomes = [{"component_type": "cpu", "model": "CPU X", "realized_value": value} for value in (70, 80, 90)]
    result = lookup("cpu", "CPU X", catalog, outcomes)
    assert result.source == "purchase_outcomes"
    assert result.median == 80
