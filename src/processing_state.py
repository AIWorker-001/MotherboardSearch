#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

STATE_SCHEMA_VERSION = 1
DEFAULT_RETENTION_DAYS = 7


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def detector_version(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item)):
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": STATE_SCHEMA_VERSION, "updated_at": None, "entries": []}
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported state schema: {state.get('schema_version')}")
    state.setdefault("entries", [])
    return state


def prune_state(state: dict[str, Any], *, now: datetime, retention_days: int) -> int:
    cutoff = now - timedelta(days=retention_days)
    before = len(state["entries"])
    state["entries"] = [
        entry for entry in state["entries"]
        if parse_time(entry["last_seen_at"]) >= cutoff
    ]
    return before - len(state["entries"])


def processed_keys(state: dict[str, Any]) -> set[tuple[str, str]]:
    return {(str(entry["item_id"]), str(entry["detector_version"])) for entry in state["entries"]}


def select_pending(listings: list[dict[str, Any]], state: dict[str, Any], version: str) -> list[dict[str, Any]]:
    completed = processed_keys(state)
    return [listing for listing in listings if (str(listing["id"]), version) not in completed]


def merge_results(
    state: dict[str, Any],
    listings: list[dict[str, Any]],
    results: list[dict[str, Any]],
    *,
    version: str,
    now: datetime,
) -> None:
    listing_by_id = {str(item["id"]): item for item in listings}
    result_by_id = {str(item.get("item_id", item.get("id"))): item for item in results}
    existing = {
        (str(entry["item_id"]), str(entry["detector_version"])): entry
        for entry in state["entries"]
    }
    timestamp = isoformat(now)

    for item_id, listing in listing_by_id.items():
        key = (item_id, version)
        result = result_by_id.get(item_id)
        if result is None:
            continue
        entry = existing.get(key, {})
        entry.update({
            "item_id": item_id,
            "detector_version": version,
            "title": listing.get("title", result.get("title", "")),
            "url": listing.get("url", f"https://shopgoodwill.com/item/{item_id}"),
            "first_seen_at": entry.get("first_seen_at", timestamp),
            "last_seen_at": timestamp,
            "processed_at": timestamp,
            "cpu_state": result.get("cpu_state"),
            "value_score": result.get("value_score"),
            "maxima": result.get("maxima", {}),
            "gallery_count": result.get("gallery_count", 0),
        })
        existing[key] = entry

    state["entries"] = sorted(existing.values(), key=lambda entry: (entry["last_seen_at"], entry["item_id"]), reverse=True)
    state["updated_at"] = timestamp


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the rolling MotherboardSearch processing ledger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    version_parser = subparsers.add_parser("version")
    version_parser.add_argument("paths", nargs="+", type=Path)

    pending_parser = subparsers.add_parser("pending")
    pending_parser.add_argument("--listings", type=Path, required=True)
    pending_parser.add_argument("--state", type=Path, required=True)
    pending_parser.add_argument("--version", required=True)
    pending_parser.add_argument("--output", type=Path, required=True)
    pending_parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)

    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--listings", type=Path, required=True)
    merge_parser.add_argument("--results", type=Path, required=True)
    merge_parser.add_argument("--state", type=Path, required=True)
    merge_parser.add_argument("--version", required=True)
    merge_parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)

    args = parser.parse_args()
    if args.command == "version":
        print(detector_version(args.paths))
        return 0

    now = utc_now()
    state = load_state(args.state)
    removed = prune_state(state, now=now, retention_days=args.retention_days)
    listings = json.loads(args.listings.read_text(encoding="utf-8"))

    if args.command == "pending":
        pending = select_pending(listings, state, args.version)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(pending, indent=2) + "\n", encoding="utf-8")
        save_state(args.state, state)
        print(json.dumps({"listings": len(listings), "pending": len(pending), "pruned": removed, "detector_version": args.version}))
        return 0

    results = json.loads(args.results.read_text(encoding="utf-8"))
    merge_results(state, listings, results, version=args.version, now=now)
    prune_state(state, now=now, retention_days=args.retention_days)
    save_state(args.state, state)
    print(json.dumps({"merged": len(results), "ledger_entries": len(state["entries"]), "pruned": removed, "detector_version": args.version}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
