#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description='Create a reproducible release manifest')
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path, default=Path('release-manifest.json'))
    args = parser.parse_args()
    root = args.root.resolve()
    files = []
    for directory in ('src', 'config', 'data'):
        for path in sorted((root / directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                files.append({'path': str(path.relative_to(root)), 'sha256': sha256(path), 'bytes': path.stat().st_size})
    manifest = {
        'schema_version': 1,
        'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'files': files,
    }
    args.output.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'files': len(files), 'output': str(args.output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
