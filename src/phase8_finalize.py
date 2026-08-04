#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(command: list[str], root: Path) -> None:
    print('+', ' '.join(command), flush=True)
    subprocess.run(command, cwd=root, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='Finalize a daily run with health, history, and reports')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('config/operations.json'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = json.loads(args.config.read_text(encoding='utf-8'))
    output = args.output_dir
    run_report = output / 'run_report.json'
    production = output / 'production_detector_report.json'
    values = output / 'phase4_value_report.json'
    health = output / 'operations_health.json'
    run([sys.executable, 'src/operations_health.py', '--run-report', str(run_report), '--production-results', str(production), '--config', str(args.config), '--output', str(health)], root)
    run([sys.executable, 'src/run_history.py', '--history', config['run_history'], '--run-report', str(run_report), '--retention-days', str(config['retention_days'])], root)
    run([sys.executable, 'src/daily_report.py', '--values', str(values), '--run-report', str(run_report), '--health', str(health), '--config', str(args.config), '--json-output', config['report']['output_json'], '--html-output', config['report']['output_html']], root)
    print(json.dumps({'health': str(health), 'report_json': config['report']['output_json'], 'report_html': config['report']['output_html']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
