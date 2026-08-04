#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_registered_model(model: dict[str, Any], root: Path | None = None) -> tuple[bool, str | None, Path]:
    weights = Path(model['weights'])
    if not weights.is_absolute() and root is not None:
        weights = root / weights
    if not weights.exists():
        return False, 'weights_missing', weights
    expected = str(model.get('sha256', ''))
    if not expected:
        return False, 'sha256_missing', weights
    if sha256(weights) != expected:
        return False, 'sha256_mismatch', weights
    return True, None, weights
