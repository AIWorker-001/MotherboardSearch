import json
from pathlib import Path

from src.config_validator import validate_repository


def test_current_repository_config_is_valid():
    root = Path('.')
    release = json.loads(Path('config/release.json').read_text())
    assert validate_repository(root.resolve(), release) == []
