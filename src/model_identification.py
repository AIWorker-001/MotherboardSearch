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

BOARD_PATTERNS = [
    re.compile(r"\b(?:ASUS|MSI|GIGABYTE|ASROCK|EVGA|SUPERMICRO|BIOSTAR|INTEL)\b[^\n]{0,100}?\b(?:Z|B|H|X|A|Q|C|W)[0-9]{2,3}[A-Z0-9-]*\b[^\n]{0,80}", re.I),
    re.compile(r"\b(?:MAXIMUS|STRIX|AORUS|TOMAHAWK|MORTAR|GAMING|DESIGNARE|STEEL LEGEND|TAICHI|PRIME|PROART)\b[^\n]{0,100}", re.I),
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
    stated_text: str | None = None
    confirmation: str | None = None


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
        canonical = normalize_text(key)
        score = SequenceMatcher(None, normalized, canonical).ratio()
        if canonical in normalized or normalized in canonical:
            score = max(score, 0.92)
        if score > best_score:
            best_key, best_score = key, score
    return best_key, best_score


def best_candidate_match(candidates: list[str], catalog_keys: Iterable[str]) -> tuple[str | None, float, str | None]:
    best_key, best_score, best_candidate = None, 0.0, None
    ordered_candidates = sorted(candidates, key=candidate_specificity, reverse=True)
    for candidate in ordered_candidates:
        tokens = set(normalize_text(candidate).split())
        if tokens and tokens.issubset(GENERIC_MODEL_TOKENS):
            continue
        key, score = best_catalog_match(candidate, catalog_keys)
        if key and (score > best_score or (abs(score - best_score) < 0.03 and candidate_specificity(candidate) > candidate_specificity(best_candidate or ""))):
            best_key, best_score, best_candidate = key, score, candidate
    return best_key, best_score, best_candidate




def structured_model_tokens(value: str) -> dict[str, str | None]:
    normalized = normalize_text(value)
    manufacturer = next((name for name in ("ASUS", "MSI", "GIGABYTE", "ASROCK", "EVGA", "SUPERMICRO", "BIOSTAR", "INTEL") if name in normalized.split()), None)
    chipset_match = re.search(r"\b([ZBHXAQCW][0-9]{2,3})\b", normalized)
    suffix_match = re.search(r"\b([ZBHXAQCW][0-9]{2,3})[- ]?([A-Z0-9]+)\b", normalized)
    family_tokens = [token for token in normalized.split() if token in {"PRIME", "MAXIMUS", "STRIX", "AORUS", "TOMAHAWK", "MORTAR", "GAMING", "DESIGNARE", "TAICHI", "PROART"}]
    return {
        "manufacturer": manufacturer,
        "chipset": chipset_match.group(1) if chipset_match else None,
        "suffix": suffix_match.group(2) if suffix_match and suffix_match.group(2) != (chipset_match.group(1) if chipset_match else None) else None,
        "family": family_tokens[0] if family_tokens else None,
        "normalized": normalized,
    }


def exact_model_conflict(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    a, b = structured_model_tokens(left), structured_model_tokens(right)
    for key in ("manufacturer", "chipset", "family"):
        if a[key] and b[key] and a[key] != b[key]:
            return True
    if a["suffix"] and b["suffix"] and a["suffix"] != b["suffix"]:
        return True
    return False

def candidate_agreement(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    a, b = normalize_text(left), normalize_text(right)
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def listing_text(item: dict) -> str:
    gallery = item.get("gallery") or {}
    structured = gallery.get("structured_details", [])
    return "\n".join([
        str(item.get("title", "")),
        str(item.get("card", "")),
        str(gallery.get("title", "")),
        str(gallery.get("description", "")),
        "\n".join(str(value) for value in structured),
        str(gallery.get("detail_text", "")),
    ])


def resolve_identification(
    listing_candidates: list[str],
    visual_candidates: list[str],
    catalog_keys: Iterable[str],
) -> tuple[Identification | None, dict]:
    catalog_keys = list(catalog_keys)
    listing_key, listing_score, listing_raw = best_candidate_match(listing_candidates, catalog_keys)
    visual_key, visual_score, visual_raw = best_candidate_match(visual_candidates, catalog_keys)
    if listing_raw and (listing_key is None or listing_score < 0.60):
        listing_key = None
    if visual_raw and (visual_key is None or visual_score < 0.60):
        visual_key = None
    agreement = candidate_agreement(listing_key or listing_raw, visual_key or visual_raw)
    model_conflict = exact_model_conflict(listing_key or listing_raw, visual_key or visual_raw)

    audit = {
        "listing_candidate": listing_raw,
        "listing_catalog_match": listing_key,
        "listing_match_score": round(listing_score, 4),
        "visual_candidate": visual_raw,
        "visual_catalog_match": visual_key,
        "visual_match_score": round(visual_score, 4),
        "agreement": round(agreement, 4),
        "exact_model_conflict": model_conflict,
    }

    if listing_key and listing_score >= 0.82:
        if visual_key and visual_score >= 0.75:
            if not model_conflict and agreement >= 0.82:
                confidence = min(0.995, 0.88 + 0.08 * listing_score + 0.04 * visual_score)
                return Identification(listing_key, round(confidence, 4), "listing_confirmed", listing_raw, "visual_agreement"), audit
            return Identification(listing_key, round(min(0.90, listing_score), 4), "listing_conflict", listing_raw, "visual_conflict"), audit
        return Identification(listing_key, round(min(0.94, 0.82 + 0.12 * listing_score), 4), "listing_probable", listing_raw, "not_visually_confirmed"), audit

    if listing_raw and not listing_key:
        if visual_key and visual_score >= 0.82:
            return Identification(visual_key, round(min(0.94, visual_score), 4), "visually_identified", listing_raw, "listing_uncatalogued_or_incomplete"), audit
        return Identification(listing_raw, 0.72, "listing_uncatalogued", listing_raw, "catalog_missing"), audit

    if visual_key and visual_score >= 0.82:
        return Identification(visual_key, round(min(0.94, visual_score), 4), "visually_identified", None, "listing_missing_model"), audit
    return None, audit


def identify_item(item: dict, catalog: dict, image_paths: list[Path]) -> dict:
    seller_text = listing_text(item)
    ocr_texts = [run_ocr(image_path) for image_path in image_paths]
    visual_text = "\n".join(ocr_texts)

    listing_board_candidates = extract_candidates(seller_text, BOARD_PATTERNS)
    concise_listing_model = canonical_listing_model(str(item.get("title", ""))) or canonical_listing_model(seller_text)
    if concise_listing_model:
        listing_board_candidates = [concise_listing_model] + [candidate for candidate in listing_board_candidates if normalize_text(candidate) != normalize_text(concise_listing_model)]
    visual_board_candidates = extract_candidates(visual_text, BOARD_PATTERNS)
    listing_cpu_candidates = extract_candidates(seller_text, CPU_PATTERNS)
    visual_cpu_candidates = extract_candidates(visual_text, CPU_PATTERNS)

    board, board_audit = resolve_identification(listing_board_candidates, visual_board_candidates, catalog.get("motherboards", {}).keys())
    cpu, cpu_audit = resolve_identification(listing_cpu_candidates, visual_cpu_candidates, catalog.get("cpus", {}).keys())

    return {
        "item_id": str(item["id"]),
        "motherboard": asdict(board) if board else None,
        "cpu": asdict(cpu) if cpu else None,
        "listing_board_candidates": listing_board_candidates,
        "visual_board_candidates": visual_board_candidates,
        "listing_cpu_candidates": listing_cpu_candidates,
        "visual_cpu_candidates": visual_cpu_candidates,
        "motherboard_audit": board_audit,
        "cpu_audit": cpu_audit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prioritize seller-stated models, then confirm with OCR or identify visually")
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
    print(json.dumps({
        "items": len(output),
        "identified_boards": sum(bool(x["motherboard"]) for x in output),
        "listing_confirmed": sum(x.get("motherboard", {}).get("source") == "listing_confirmed" for x in output if x.get("motherboard")),
        "listing_conflicts": sum(x.get("motherboard", {}).get("source") == "listing_conflict" for x in output if x.get("motherboard")),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Model tokens that are too generic to identify a board by themselves.
GENERIC_MODEL_TOKENS = {
    "AORUS", "GAMING", "PRIME", "STRIX", "MAXIMUS", "TOMAHAWK", "MORTAR",
    "MOTHERBOARD", "ATX", "MICRO-ATX", "MINI-ITX", "DDR4", "DDR5",
}


def canonical_listing_model(text: str) -> str | None:
    """Extract the concise seller-stated board model without descriptive tail text."""
    normalized = normalize_text(text)
    patterns = [
        r"\b(ASUS)\s+(P[0-9][A-Z0-9-]{2,}(?:\s+EVO|\s+PRO|\s+DELUXE|\s+LE|\s+PLUS)?)\b",
        r"\b(ASUS)\s+(M[0-9][A-Z0-9-]{2,}(?:\s+PRO(?:\s+USB3)?|\s+EVO)?)\b",
        r"\b(GIGABYTE)\s+(GA-[A-Z0-9-]+)\b",
        r"\b(GIGABYTE)\s+([ZBHX][0-9]{3}\s+AORUS\s+(?:GAMING\s+[0-9]+|ELITE(?:\s+AX)?|PRO(?:\s+AX)?|MASTER|M))\b",
        r"\b(GIGABYTE)\s+(B[0-9]{3}\s+AORUS\s+M)\b",
        r"\b(ASROCK)\s+(FATAL1TY\s+[ZBHX][0-9]{3}\s+GAMING-ITX(?:\s+AC)?)\b",
        r"\b(ASROCK)\s+([ZBHX][0-9]{3}\s+STEEL\s+LEGEND)\b",
        r"\b(MSI)\s+([ZBHX][0-9]{3}[A-Z]?\s+GAMING\s+M[357])\b",
        r"\b(MSI)\s+([ZBHX][0-9]{3}\s+TOMAHAWK(?:\s+MAX)?)\b",
        r"\b(ASUS)\s+(B[0-9]{2,3}M-[A-Z0-9]+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return f"{match.group(1)} {match.group(2)}"
    return None


def candidate_specificity(candidate: str) -> tuple[int, int]:
    tokens = normalize_text(candidate).split()
    informative = [token for token in tokens if token not in GENERIC_MODEL_TOKENS]
    has_chipset = 1 if re.search(r"\b[ZBHXAQCW][0-9]{2,3}\b", normalize_text(candidate)) else 0
    return (has_chipset * 100 + len(informative), len(candidate))
