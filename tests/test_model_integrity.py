from pathlib import Path

from src.model_integrity import sha256, verify_registered_model


def test_model_integrity(tmp_path: Path):
    weights = tmp_path / 'model.pt'
    weights.write_bytes(b'weights')
    model = {'weights': str(weights), 'sha256': sha256(weights)}
    valid, reason, resolved = verify_registered_model(model)
    assert valid
    assert reason is None
    assert resolved == weights
    weights.write_bytes(b'changed')
    valid, reason, _ = verify_registered_model(model)
    assert not valid
    assert reason == 'sha256_mismatch'
