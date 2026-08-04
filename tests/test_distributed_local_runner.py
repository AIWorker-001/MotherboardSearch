from src.distributed_local_runner import run_task


def test_local_runner_executes_command(tmp_path):
    task = {'shard': 0, 'command': ['python3', '-c', 'print("ok")'], 'output_dir': str(tmp_path)}
    result = run_task(task, tmp_path)
    assert result['returncode'] == 0
    assert 'ok' in result['stdout']
