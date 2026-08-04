#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from PIL import Image

BOARD_PATTERNS = [
    re.compile(r"\b(?:ASUS|MSI|GIGABYTE|ASROCK|EVGA)\b[^\n]{0,80}?\b(?:Z|B|H|X|A)[0-9]{3}[A-Z0-9-]*\b[^\n]{0,60}", re.I),
    re.compile(r"\b(?:MAXIMUS|STRIX|AORUS|TOMAHAWK|GAMING|DESIGNARE|STEEL LEGEND|TAICHI)\b[^\n]{0,80}", re.I),
]
CPU_PATTERNS = [
    re.compile(r"\bINTEL\s+(?:CORE\s+)?I[3579][ -]?[0-9]{4,5}[A-Z]{0,2}\b", re.I),
    re.compile(r"\bAMD\s+RYZEN\s+[3579]\s+[0-9]{4}[A-Z0-9]{0,3}\b", re.I),
    re.compile(r"\bRYZEN\s+[3579]\s+[0-9]{4}[A-Z0-9]{0,3}\b", re.I),
]


@dataclass
class Identification:
    text: str
    confidence: float
    source: str


def normalize_text(value: str) -> str:
    value = re.sub(r"[^A-Z0-9+ -]+", " ", value.upper())
    return re.sub(r"\s+", " ", value).strip()


def run_ocr(path: Path) -> str:
    try:
        return subprocess.run(
            ["tesseract", str(path), "stdout", "--psm", "11"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def extract_candidates(text: str, patterns: Iterable[re.Pattern[str]]) -> list[str]:
    candidates: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = normalize_text(match.group(0))
            if value and value not in candidates:
                candidates.append(value)
    return candidates


def best_catalog_match(candidate: str, catalog_keys: Iterable[str]) -> tuple[str | None, float]:
    normalized = normalize_text(candidate)
    best_key, best_score = None, 0.0
    for key in catalog_keys:
        score = SequenceMatcher(None, normalized, normalize_text(key)).ratio()
        if normalize_text(key) in normalized or normalized in normalize_text(key):
            score = max(score, 0.92)
        if score > best_score:
            best_key, best_score = key, score
    return best_key, best_score


def identify_item(item: dict, catalog: dict, image_paths: list[Path]) -> dict:
    texts = [str(item.get("title", "")), str(item.get("card", ""))]
    for image_path in image_paths:
        texts.append(run_ocr(image_path))
    combined = "\n".join(texts)
    board_candidates = extract_candidates(combined, BOARD_PATTERNS)
    cpu_candidates = extract_candidates(combined, CPU_PATTERNS)

    board_match = None
    for candidate in board_candidates:
        key, score = best_catalog_match(candidate, catalog.get("motherboards", {}).keys())
        if key and (board_match is None or score > board_match.confidence):
            board_match = Identification(key, round(score, 4), "title_or_ocr")
    cpu_match = None
    for candidate in cpu_candidates:
        key, score = best_catalog_match(candidate, catalog.get("cpus", {}).keys())
        if key and (cpu_match is None or score > cpu_match.confidence):
            cpu_match = Identification(key, round(score, 4), "title_or_ocr")

    return {
        "item_id": str(item["id"]),
        "motherboard": asdict(board_match) if board_match else None,
        "cpu": asdict(cpu_match) if cpu_match else None,
        "board_candidates": board_candidates,
        "cpu_candidates": cpu_candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Identify motherboard and CPU models from titles and cached images")
    parser.add_argument("--listings", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("config/market_values.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    listings = json.loads(args.listings.read_text(encoding="utf-8"))
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    output = []
    for item in listings:
        item_id = str(item["id"])
        images = sorted(args.cache_dir.glob(f"{item_id}_*.jpg"))
        output.append(identify_item(item, catalog, images))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"items": len(output), "identified_boards": sum(bool(x["motherboard"]) for x in output), "identified_cpus": sum(bool(x["cpu"]) for x in output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
