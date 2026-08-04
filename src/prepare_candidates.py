#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from processing_state import listing_fingerprint


def main() -> int:
    parser = argparse.ArgumentParser(description="Join listings with galleries and compute listing fingerprints")
    parser.add_argument("--listings", type=Path, required=True)
    parser.add_argument("--galleries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    listings = json.loads(args.listings.read_text(encoding="utf-8"))
    galleries = json.loads(args.galleries.read_text(encoding="utf-8"))
    gallery_by_id = {str(item["id"]): item for item in galleries}
    candidates = []
    for listing in listings:
        item_id = str(listing["id"])
        gallery = gallery_by_id.get(item_id, {"id": item_id, "urls": [], "error": "gallery_missing"})
        candidate = dict(listing)
        candidate["gallery"] = gallery
        candidate["listing_hash"] = listing_fingerprint(listing, gallery)
        candidates.append(candidate)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(candidates, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"listings": len(listings), "galleries": len(galleries), "candidates": len(candidates)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
