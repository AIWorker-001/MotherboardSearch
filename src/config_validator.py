#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate_json(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception as error:
        return [f'{path}:invalid_json:{error}']
    if 'schema_version' not in payload:
        errors.append(f'{path}:missing_schema_version')
    return errors


def validate_repository(root: Path, release_config: dict) -> list[str]:
    errors: list[str] = []
    for relative in release_config.get('required_files', []):
        path = root / relative
        if not path.exists():
            errors.append(f'{relative}:missing')
        elif path.suffix == '.json':
            errors.extend(validate_json(path))
    distributed = json.loads((root / 'config/distributed.json').read_text(encoding='utf-8'))
    if int(distributed['default_shards']) > int(distributed['maximum_shards']):
        errors.append('config/distributed.json:default_shards_exceeds_maximum')
    operations = json.loads((root / 'config/operations.json').read_text(encoding='utf-8'))
    if int(operations['retention_days']) < 1:
        errors.append('config/operations.json:invalid_retention_days')
    training = json.loads((root / 'config/training.json').read_text(encoding='utf-8'))
    ratios = training['dataset']
    total = float(ratios['train_ratio']) + float(ratios['validation_ratio']) + float(ratios['test_ratio'])
    if abs(total - 1.0) > 1e-6:
        errors.append('config/training.json:dataset_ratios_must_sum_to_one')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate MotherboardSearch configuration before a release or daily run')
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--release-config', type=Path, default=Path('config/release.json'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    release = json.loads(args.release_config.read_text(encoding='utf-8'))
    errors = validate_repository(args.root.resolve(), release)
    report = {'valid': not errors, 'errors': errors}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
