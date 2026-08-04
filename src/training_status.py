#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from continual_learning import labeled_image_count, should_train, now_utc


def main() -> int:
    parser = argparse.ArgumentParser(description='Report continual-learning readiness')
    parser.add_argument('--config', type=Path, default=Path('config/continual_learning.json'))
    parser.add_argument('--annotations', type=Path, default=Path('data/annotations/annotations.json'))
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    state = json.loads(Path(config['state_file']).read_text(encoding='utf-8'))
    annotations = json.loads(args.annotations.read_text(encoding='utf-8'))
    count = labeled_image_count(annotations)
    eligible, reasons = should_train(config, state, count, now=now_utc())
    print(json.dumps({'eligible': eligible, 'reasons': reasons, 'labeled_images': count, 'state': state}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
