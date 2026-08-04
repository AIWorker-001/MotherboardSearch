from src.evaluate_detector import promotion_decision


def test_promotion_thresholds():
    thresholds = {"minimum_map50": 0.7, "minimum_precision": 0.8, "minimum_recall": 0.75}
    assert promotion_decision({"map50": 0.8, "precision": 0.85, "recall": 0.8}, thresholds)[0]
    promotable, failures = promotion_decision({"map50": 0.6, "precision": 0.85, "recall": 0.8}, thresholds)
    assert not promotable
    assert failures == ["map50"]
