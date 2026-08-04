from pathlib import Path

from src.release_manifest import sha256


def test_sha256(tmp_path: Path):
    path = tmp_path / 'x'
    path.write_bytes(b'abc')
    assert len(sha256(path)) == 64
