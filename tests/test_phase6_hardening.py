from pathlib import Path


def test_manifest_is_built_even_when_phase2_off():
    source = Path('src/daily_run.py').read_text(encoding='utf-8')
    build_pos = source.index('src/build_local_manifest.py')
    conditional_pos = source.index('if args.phase2 != "off":', build_pos)
    assert build_pos < conditional_pos


def test_monitoring_is_nonfatal():
    source = Path('src/inference_monitor.py').read_text(encoding='utf-8')
    assert 'return 2 if reasons else 0' not in source


def test_phase6_files_affect_detector_version():
    source = Path('src/daily_run.py').read_text(encoding='utf-8')
    assert 'ROOT / "src" / "production_detector.py"' in source
    assert 'ROOT / "config" / "deployment.json"' in source
