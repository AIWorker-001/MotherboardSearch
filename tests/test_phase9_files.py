from pathlib import Path


def test_phase9_distributed_components_exist():
    assert Path('config/distributed.json').exists()
    assert Path('src/shard_work.py').exists()
    assert Path('src/distributed_state.py').exists()
    assert Path('src/process_shard.py').exists()
    assert Path('src/merge_shards.py').exists()
