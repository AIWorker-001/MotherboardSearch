from pathlib import Path


def test_daily_run_supports_distributed_modes():
    source = Path('src/daily_run.py').read_text(encoding='utf-8')
    assert 'choices=("off", "plan", "local")' in source
    assert 'src/distributed_local_runner.py' in source
    assert 'src/merge_shards.py' in source
