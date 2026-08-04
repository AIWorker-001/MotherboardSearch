from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))
import motherboard_search as module


def test_score_cooler_attached():
    maxima = {key: 0.0 for key in module.PROMPTS}
    maxima["intel_cooler"] = 0.80
    maxima["empty_socket"] = 0.20
    maxima["socket_cover"] = 0.10
    state, score = module.score_state(maxima)
    assert state == "cooler_attached_cpu_highly_likely"
    assert score == 100


def test_score_empty_socket():
    maxima = {key: 0.0 for key in module.PROMPTS}
    maxima["empty_socket"] = 0.90
    maxima["cpu_visible"] = 0.10
    state, score = module.score_state(maxima)
    assert state == "empty_socket_likely"
    assert score == -100
