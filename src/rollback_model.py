#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Disable trained production inference and return to fallback")
    parser.add_argument("--deployment", type=Path, default=Path("config/deployment.json"))
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    deployment = json.loads(args.deployment.read_text(encoding="utf-8"))
    deployment["mode"] = "fallback"
    deployment["rollback_reason"] = args.reason
    args.deployment.write_text(json.dumps(deployment, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": "fallback", "reason": args.reason}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
