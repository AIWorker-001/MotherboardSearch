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
    parser = argparse.ArgumentParser(description='Process one deterministic MotherboardSearch shard')
    parser.add_argument('--shard', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--phase2-model', default='IDEA-Research/grounding-dino-tiny')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    rows = json.loads(args.shard.read_text(encoding='utf-8'))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidates = args.output_dir / 'candidates.json'
    galleries = args.output_dir / 'galleries.json'
    manifest = args.output_dir / 'manifest.json'
    cache = args.output_dir / 'cache'
    legacy = args.output_dir / 'legacy.json'
    phase2 = args.output_dir / 'phase2.json'
    merged = args.output_dir / 'results.json'
    candidates.write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    run([sys.executable, 'src/extract_pending_galleries.py', '--candidates', str(candidates), '--output', str(galleries)], root)
    run([sys.executable, 'src/motherboard_search.py', '--galleries', str(galleries), '--output', str(legacy), '--cache-dir', str(cache), '--errors', str(args.output_dir / 'download_errors.json')], root)
    run([sys.executable, 'src/build_local_manifest.py', '--galleries', str(galleries), '--cache-dir', str(cache), '--output', str(manifest)], root)
    run([sys.executable, 'src/phase2_detector.py', '--manifest', str(manifest), '--model', args.phase2_model, '--output', str(phase2), '--annotated-dir', str(args.output_dir / 'annotated')], root)
    run([sys.executable, 'src/merge_detector_results.py', '--legacy', str(legacy), '--phase2', str(phase2), '--mode', 'on', '--output', str(merged)], root)
    print(json.dumps({'items': len(rows), 'result': str(merged)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
