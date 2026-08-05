from pathlib import Path


def test_daily_run_supports_distributed_modes():
    source = Path('src/daily_run.py').read_text(encoding='utf-8')
    assert 'choices=("off", "plan", "local")' in source
    assert 'src/distributed_local_runner.py' in source
    assert 'src/merge_shards.py' in source


def test_phase2_uses_specialized_detector_passes():
    source = Path('src/phase2_detector.py').read_text(encoding='utf-8')
    assert '--passes' in source
    assert 'groups={detector_group}' in source


def test_daily_run_builds_reference_gap_queue():
    source = Path('src/daily_run.py').read_text(encoding='utf-8')
    assert 'src/reference_gap_queue.py' in source
    assert 'reference_gap_queue' in source


def test_daily_run_builds_reference_discovery_plan():
    source = Path('src/daily_run.py').read_text(encoding='utf-8')
    assert 'src/reference_discovery.py' in source
    assert 'reference_discovery_plan' in source


def test_daily_run_exports_reference_region_crops():
    source=Path('src/daily_run.py').read_text(encoding='utf-8')
    assert '--region-output-dir' in source
    assert 'reference_region_crops' in source


def test_daily_run_reconciles_reference_socket_detection_before_valuation():
    source = Path('src/daily_run.py').read_text(encoding='utf-8')
    assert 'src/socket_region_detector.py' in source
    assert 'src/reconcile_socket_results.py' in source
    assert source.index('src/reconcile_socket_results.py') < source.index('src/value_engine.py', source.index('src/reconcile_socket_results.py'))
