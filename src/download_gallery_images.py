#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from motherboard_search import build_http_session, download_image


def main() -> int:
    parser = argparse.ArgumentParser(description="Download gallery images without running legacy CLIP scoring")
    parser.add_argument("--galleries", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--errors", type=Path, required=True)
    parser.add_argument("--download-workers", type=int, default=8)
    args = parser.parse_args()

    galleries = json.loads(args.galleries.read_text(encoding="utf-8"))
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    errors = []
    session = build_http_session()
    futures = {}
    with ThreadPoolExecutor(max_workers=max(1, args.download_workers)) as executor:
        for item in galleries:
            for index, url in enumerate(item.get("urls", []), start=1):
                future = executor.submit(download_image, session, str(item["id"]), index, url, args.cache_dir)
                futures[future] = (str(item["id"]), index, url)
        for future in as_completed(futures):
            item_id, index, url = futures[future]
            try:
                future.result()
            except Exception as error:
                errors.append({"item_id": item_id, "image": index, "url": url, "error": str(error)})
    session.close()
    args.errors.parent.mkdir(parents=True, exist_ok=True)
    args.errors.write_text(json.dumps(errors, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"images_requested": len(futures), "errors": len(errors)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
