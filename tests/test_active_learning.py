from src.build_review_queue import score_candidate


def test_uncertain_disagreement_has_high_priority():
    weights = {"uncertainty_weight": 0.55, "disagreement_weight": 0.30, "novelty_weight": 0.15}
    uncertain = {"cpu_confidence": 0.3, "review_reasons": ["detector_disagreement"], "identification": {"motherboard": None}}
    confident = {"cpu_confidence": 0.95, "review_reasons": [], "identification": {"motherboard": {"text": "known"}}}
    assert score_candidate(uncertain, weights) > score_candidate(confident, weights)
