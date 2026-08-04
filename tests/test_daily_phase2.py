from pathlib import Path


def test_daily_runner_versions_phase2_files():
    source = Path("src/daily_run.py").read_text(encoding="utf-8")
    assert 'ROOT / "src" / "object_detector.py"' in source
    assert 'ROOT / "config" / "detection_classes.json"' in source
    assert 'choices=("on", "off", "only")' in source
    assert 'src/phase2_detector.py' in source
    assert 'src/merge_detector_results.py' in source
