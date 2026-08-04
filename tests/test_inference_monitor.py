from src.inference_monitor import detect_drift, summarize


def test_summary_and_drift():
    current = summarize([
        {"cpu_confidence": 0.3, "needs_review": True, "cpu_state": "unclear"},
        {"cpu_confidence": 0.4, "needs_review": True, "cpu_state": "unclear"},
    ])
    baseline = {"sample_count": 100, "mean_confidence": 0.8, "review_rate": 0.1, "class_frequencies": {"visible_cpu_likely": 0.8}}
    config = {"confidence_drop": 0.15, "review_rate_limit": 0.45, "class_frequency_delta": 0.25}
    reasons = detect_drift(current, baseline, config)
    assert "confidence_drop" in reasons
    assert "review_rate" in reasons
    assert "class_frequency_shift" in reasons
