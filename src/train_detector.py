#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a dedicated motherboard detector with Ultralytics")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/training.json"))
    parser.add_argument("--project", type=Path, default=Path("models/runs"))
    parser.add_argument("--name")
    args = parser.parse_args()
    try:
        from ultralytics import YOLO
    except ImportError as error:
        raise SystemExit("Install ultralytics with: python3 -m pip install ultralytics") from error
    config = json.loads(args.config.read_text(encoding="utf-8"))["training"]
    name = args.name or datetime.now(timezone.utc).strftime("detector-%Y%m%d-%H%M%S")
    model = YOLO(config["base_model"])
    result = model.train(
        data=str(args.dataset),
        epochs=int(config["epochs"]),
        imgsz=int(config["image_size"]),
        batch=int(config["batch_size"]),
        patience=int(config["patience"]),
        workers=int(config["workers"]),
        project=str(args.project),
        name=name,
    )
    print(json.dumps({"run": name, "save_dir": str(result.save_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
