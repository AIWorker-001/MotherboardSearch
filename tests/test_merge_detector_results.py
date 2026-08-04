from src.merge_detector_results import merge_item


def test_phase2_only_mode_uses_spatial_result():
    phase2 = {"item_id": "1", "cpu_state": "visible_cpu_likely", "value_score": 80}
    merged = merge_item(None, phase2, "only")
    assert merged["detector_source"] == "phase2_spatial"


def test_combined_mode_marks_disagreement_for_review():
    legacy = {"item_id": "1", "cpu_state": "empty_socket_likely", "value_score": -100, "maxima": {}}
    phase2 = {"item_id": "1", "cpu_state": "visible_cpu_likely", "value_score": 80, "needs_review": False, "review_reasons": []}
    merged = merge_item(legacy, phase2, "on")
    assert merged["needs_review"]
    assert "detector_disagreement" in merged["review_reasons"]
    assert merged["legacy"]["cpu_state"] == "empty_socket_likely"


def test_combined_mode_falls_back_when_phase2_missing():
    legacy = {"item_id": "1", "cpu_state": "unclear", "value_score": 0}
    merged = merge_item(legacy, None, "on")
    assert merged["detector_source"] == "legacy_fallback"
    assert merged["needs_review"]
