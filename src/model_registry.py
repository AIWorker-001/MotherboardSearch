#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Register and promote trained motherboard detector models")
    parser.add_argument("--registry", type=Path, default=Path("models/registry/registry.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    register = subparsers.add_parser("register")
    register.add_argument("--name", required=True)
    register.add_argument("--weights", type=Path, required=True)
    register.add_argument("--evaluation", type=Path, required=True)
    promote = subparsers.add_parser("promote")
    promote.add_argument("--name", required=True)
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    if args.command == "register":
        evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
        registry["models"] = [model for model in registry["models"] if model["name"] != args.name]
        registry["models"].append({
            "name": args.name,
            "weights": str(args.weights),
            "sha256": sha256(args.weights),
            "evaluation": evaluation,
            "registered_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        })
    else:
        model = next((model for model in registry["models"] if model["name"] == args.name), None)
        if model is None:
            raise ValueError("Model not registered")
        if not model["evaluation"].get("promotable"):
            raise ValueError("Model did not pass promotion thresholds")
        registry["active_model"] = args.name
    args.registry.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"active_model": registry["active_model"], "models": len(registry["models"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
