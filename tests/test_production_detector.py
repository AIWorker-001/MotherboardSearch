from src.production_detector import load_active_model, select_backend, stable_bucket


def test_bucket_is_stable():
    assert stable_bucket("123") == stable_bucket("123")
    assert 0 <= stable_bucket("123") <= 1


def test_no_active_model_forces_fallback():
    deployment = {"mode": "auto", "canary_fraction": 1.0}
    assert select_backend("1", deployment, None) == "fallback"


def test_trained_mode_uses_model():
    assert select_backend("1", {"mode": "trained"}, {"name": "x"}) == "trained"
