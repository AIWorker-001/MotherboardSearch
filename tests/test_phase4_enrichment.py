from pathlib import Path


def test_daily_runner_includes_phase4_files():
    source = Path("src/daily_run.py").read_text(encoding="utf-8")
    assert 'src/model_identification.py' in source
    assert 'src/market_pricing.py' in source
    assert 'src/phase4_enrichment.py' in source
    assert 'phase4_value_report.json' in source
