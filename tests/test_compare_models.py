from src.compare_models import promotion_decision


def model(map50, precision, recall, promotable=True):
    return {'evaluation': {'promotable': promotable, 'metrics': {'map50': map50, 'precision': precision, 'recall': recall}}}


def test_candidate_must_improve():
    policy = {'minimum_map50_gain': 0.02, 'minimum_precision_gain': 0.0, 'minimum_recall_gain': 0.0, 'allow_tradeoff_if_map50_gain': 0.05}
    promote, reasons, delta = promotion_decision(model(0.80, 0.85, 0.82), model(0.75, 0.84, 0.80), policy)
    assert promote
    assert delta['map50'] == 0.05
    promote, reasons, _ = promotion_decision(model(0.76, 0.85, 0.82), model(0.75, 0.84, 0.80), policy)
    assert not promote
    assert 'insufficient_map50_gain' in reasons
