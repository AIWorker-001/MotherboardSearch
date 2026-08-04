#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def command_version(command: str) -> str | None:
    path = shutil.which(command)
    if path is None:
        return None
    for args in ([command, '--version'], [command, '-v']):
        try:
            completed = subprocess.run(args, text=True, capture_output=True, timeout=10)
            text = (completed.stdout or completed.stderr).strip().splitlines()
            if text:
                return text[0]
        except Exception:
            pass
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description='Check whether this machine is ready to run MotherboardSearch')
    parser.add_argument('--config', type=Path, default=Path('config/release.json'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    commands = {command: command_version(command) for command in config['required_commands']}
    missing = [command for command, version in commands.items() if version is None]
    report = {
        'ready': not missing,
        'platform': platform.platform(),
        'python': sys.version.split()[0],
        'commands': commands,
        'missing_commands': missing,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
