#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description='Promote a continual-learning candidate when comparison policy allows it')
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--registry', type=Path, default=Path('models/registry/registry.json'))
    parser.add_argument('--config', type=Path, default=Path('config/continual_learning.json'))
    args = parser.parse_args()
    comparison = json.loads(args.comparison.read_text(encoding='utf-8'))
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if not comparison.get('promote'):
        print(json.dumps({'promoted': False, 'reasons': comparison.get('reasons', [])}))
        return 0
    if not config.get('automatic_promotion', False):
        print(json.dumps({'promoted': False, 'approval_required': True, 'candidate': args.candidate}))
        return 0
    subprocess.run([sys.executable, 'src/model_registry.py', '--registry', str(args.registry), 'promote', '--name', args.candidate], check=True)
    print(json.dumps({'promoted': True, 'candidate': args.candidate}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
