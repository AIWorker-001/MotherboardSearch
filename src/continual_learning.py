#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def labeled_image_count(annotation_store: dict[str, Any]) -> int:
    return sum(1 for image in annotation_store.get('images', []) if image.get('annotations'))


def should_train(config: dict[str, Any], state: dict[str, Any], annotation_count: int, *, now: datetime) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not config.get('enabled', True):
        reasons.append('disabled')
    if annotation_count < int(config['minimum_total_labeled_images']):
        reasons.append('insufficient_total_labels')
    new_labels = annotation_count - int(state.get('last_training_annotation_count', 0))
    if new_labels < int(config['minimum_new_labeled_images']):
        reasons.append('insufficient_new_labels')
    last_training = parse_time(state.get('last_training_at'))
    if last_training and now - last_training < timedelta(days=int(config['minimum_days_between_training'])):
        reasons.append('training_cooldown')
    if int(state.get('consecutive_failures', 0)) >= int(config['maximum_training_failures']):
        reasons.append('failure_limit')
    return not reasons, reasons


def run(command: list[str], *, cwd: Path) -> None:
    print('+', ' '.join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the continual-learning training workflow when thresholds are met')
    parser.add_argument('--config', type=Path, default=Path('config/continual_learning.json'))
    parser.add_argument('--annotations', type=Path, default=Path('data/annotations/annotations.json'))
    parser.add_argument('--training-config', type=Path, default=Path('config/training.json'))
    parser.add_argument('--registry', type=Path, default=Path('models/registry/registry.json'))
    parser.add_argument('--work-dir', type=Path, default=Path('data/training/current'))
    parser.add_argument('--runs-dir', type=Path, default=Path('models/runs'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    config = json.loads(args.config.read_text(encoding='utf-8'))
    state_path = root / config['state_file']
    state = json.loads(state_path.read_text(encoding='utf-8'))
    annotations = json.loads(args.annotations.read_text(encoding='utf-8'))
    count = labeled_image_count(annotations)
    eligible, reasons = should_train(config, state, count, now=now_utc())
    if not eligible or args.dry_run:
        print(json.dumps({'eligible': eligible, 'reasons': reasons, 'labeled_images': count, 'dry_run': args.dry_run}))
        return 0

    run([sys.executable, 'src/dataset_builder.py', '--annotations', str(args.annotations), '--config', str(args.training_config), '--output', str(args.work_dir)], cwd=root)
    run_name = now_utc().strftime('continual-%Y%m%d-%H%M%S')
    evaluation = args.runs_dir / run_name / 'evaluation.json'
    weights = args.runs_dir / run_name / 'weights' / 'best.pt'
    try:
        run([sys.executable, 'src/train_detector.py', '--dataset', str(args.work_dir / 'dataset.yaml'), '--config', str(args.training_config), '--project', str(args.runs_dir), '--name', run_name], cwd=root)
        run([sys.executable, 'src/evaluate_detector.py', '--weights', str(weights), '--dataset', str(args.work_dir / 'dataset.yaml'), '--config', str(args.training_config), '--output', str(evaluation)], cwd=root)
        run([sys.executable, 'src/model_registry.py', '--registry', str(args.registry), 'register', '--name', run_name, '--weights', str(weights), '--evaluation', str(evaluation)], cwd=root)
    except Exception:
        state['consecutive_failures'] = int(state.get('consecutive_failures', 0)) + 1
        state['last_decision'] = 'training_failed'
        state_path.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
        raise

    state.update({
        'last_training_at': isoformat(now_utc()),
        'last_training_annotation_count': count,
        'consecutive_failures': 0,
        'last_candidate': run_name,
        'last_decision': 'candidate_registered',
    })
    state_path.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'candidate': run_name, 'weights': str(weights), 'evaluation': str(evaluation)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
