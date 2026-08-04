#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def metrics(model: dict[str, Any] | None) -> dict[str, float]:
    if not model:
        return {'map50': 0.0, 'precision': 0.0, 'recall': 0.0}
    return {key: float(model.get('evaluation', {}).get('metrics', {}).get(key, 0.0)) for key in ('map50', 'precision', 'recall')}


def promotion_decision(candidate: dict[str, Any], active: dict[str, Any] | None, policy: dict[str, Any]) -> tuple[bool, list[str], dict[str, float]]:
    candidate_metrics = metrics(candidate)
    active_metrics = metrics(active)
    delta = {key: round(candidate_metrics[key] - active_metrics[key], 6) for key in candidate_metrics}
    reasons: list[str] = []
    if not candidate.get('evaluation', {}).get('promotable'):
        reasons.append('candidate_failed_absolute_thresholds')
    map_gain = delta['map50']
    tradeoff = map_gain >= float(policy['allow_tradeoff_if_map50_gain'])
    if map_gain < float(policy['minimum_map50_gain']):
        reasons.append('insufficient_map50_gain')
    if not tradeoff and delta['precision'] < float(policy['minimum_precision_gain']):
        reasons.append('precision_regression')
    if not tradeoff and delta['recall'] < float(policy['minimum_recall_gain']):
        reasons.append('recall_regression')
    return not reasons, reasons, delta


def main() -> int:
    parser = argparse.ArgumentParser(description='Compare a candidate model against the active production model')
    parser.add_argument('--registry', type=Path, default=Path('models/registry/registry.json'))
    parser.add_argument('--config', type=Path, default=Path('config/continual_learning.json'))
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding='utf-8'))
    config = json.loads(args.config.read_text(encoding='utf-8'))
    candidate = next((model for model in registry.get('models', []) if model['name'] == args.candidate), None)
    if candidate is None:
        raise ValueError('candidate not registered')
    active_name = registry.get('active_model')
    active = next((model for model in registry.get('models', []) if model['name'] == active_name), None)
    promote, reasons, delta = promotion_decision(candidate, active, config['candidate_comparison'])
    report = {'candidate': args.candidate, 'active': active_name, 'promote': promote, 'reasons': reasons, 'metric_delta': delta}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
