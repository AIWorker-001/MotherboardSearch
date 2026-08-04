#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported annotation schema")
    payload.setdefault("images", [])
    return payload


def image_id(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:20]


def upsert_image(store: dict[str, Any], *, path: str, item_id: str | None = None, source: str = "shopgoodwill") -> dict[str, Any]:
    identifier = image_id(path)
    existing = next((row for row in store["images"] if row["image_id"] == identifier), None)
    if existing is None:
        existing = {
            "image_id": identifier,
            "path": path,
            "item_id": item_id,
            "source": source,
            "width": None,
            "height": None,
            "annotations": [],
            "review": {"status": "unlabeled", "reviewer": None, "updated_at": now_iso()},
        }
        store["images"].append(existing)
    return existing


def add_box(image: dict[str, Any], *, label: str, box: list[float], reviewer: str, confidence: float = 1.0) -> None:
    if len(box) != 4:
        raise ValueError("box must be [x1, y1, x2, y2]")
    x1, y1, x2, y2 = (float(value) for value in box)
    if x2 <= x1 or y2 <= y1:
        raise ValueError("box must have positive area")
    image["annotations"].append({
        "label": label,
        "box": [x1, y1, x2, y2],
        "confidence": float(confidence),
        "reviewer": reviewer,
        "created_at": now_iso(),
    })
    image["review"] = {"status": "labeled", "reviewer": reviewer, "updated_at": now_iso()}


def save_store(path: Path, store: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage MotherboardSearch bounding-box annotations")
    parser.add_argument("--store", type=Path, default=Path("data/annotations/annotations.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_image = subparsers.add_parser("add-image")
    add_image.add_argument("--path", required=True)
    add_image.add_argument("--item-id")

    add_box_parser = subparsers.add_parser("add-box")
    add_box_parser.add_argument("--path", required=True)
    add_box_parser.add_argument("--item-id")
    add_box_parser.add_argument("--label", required=True)
    add_box_parser.add_argument("--box", nargs=4, type=float, required=True)
    add_box_parser.add_argument("--reviewer", required=True)

    args = parser.parse_args()
    store = load_store(args.store)
    image = upsert_image(store, path=args.path, item_id=getattr(args, "item_id", None))
    if args.command == "add-box":
        if args.label not in store["classes"]:
            raise ValueError(f"Unknown class: {args.label}")
        add_box(image, label=args.label, box=args.box, reviewer=args.reviewer)
    save_store(args.store, store)
    print(json.dumps({"image_id": image["image_id"], "annotations": len(image["annotations"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
