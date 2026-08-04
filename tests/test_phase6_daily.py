from pathlib import Path


def test_daily_pipeline_routes_through_production_detector():
    source = Path("src/daily_run.py").read_text(encoding="utf-8")
    assert 'src/production_detector.py' in source
    assert 'src/inference_monitor.py' in source
    assert 'production_detector_report.json' in source
