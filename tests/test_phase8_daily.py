from pathlib import Path


def test_daily_run_finalizes_operations():
    source = Path('src/daily_run.py').read_text(encoding='utf-8')
    assert 'src/phase8_finalize.py' in source
    assert 'config" / "operations.json' in source
