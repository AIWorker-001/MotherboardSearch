from src.model_identification import best_catalog_match, extract_candidates, normalize_text, CPU_PATTERNS


def test_normalization_and_catalog_match():
    assert normalize_text("Intel Core i7-9700K") == "INTEL CORE I7-9700K"
    key, score = best_catalog_match("Intel Core i7 9700K", ["INTEL CORE I7-9700K"])
    assert key == "INTEL CORE I7-9700K"
    assert score > 0.8


def test_cpu_candidate_extraction():
    candidates = extract_candidates("CPU: AMD Ryzen 7 5700X installed", CPU_PATTERNS)
    assert any("RYZEN 7 5700X" in value for value in candidates)
