# MotherboardSearch

MotherboardSearch uses Playwright and image scoring to find low-cost ShopGoodwill motherboard listings that may include enough hardware to become inexpensive AIWorker nodes.

## Pipeline

1. Search ShopGoodwill through the normal home-page search field.
2. Collect listing IDs, titles, prices, and remaining auction time.
3. Open each listing and extract only images from the real `.image-gallery` component.
4. Score full images and overlapping crops for:
   - Intel stock cooler
   - AMD Wraith cooler
   - tower cooler
   - visible CPU heat spreader
   - empty CPU socket
   - socket cover
   - installed RAM
   - installed NVMe SSD
5. Return a conservative CPU state and AIWorker value score.

## Setup

```bash
npm install
npx playwright install chromium
python3 -m pip install -r requirements.txt
```

## Search

```bash
node src/search_shopgoodwill.js --query motherboard --pages 3 --output output/listings.json
```

## Extract galleries

```bash
jq -r '.[].id' output/listings.json > output/item_ids.txt
node src/collect_true_galleries.js \
  --ids-file output/item_ids.txt \
  --output output/true_galleries.json
```

## Score galleries

```bash
python3 src/motherboard_search.py \
  --galleries output/true_galleries.json \
  --output output/worker_value_report.json \
  --cache-dir cache/images
```

## Current scoring

- Cooler attached and clearly stronger than empty/cover evidence: `+100`
- Visible CPU and clearly stronger than empty evidence: `+80`
- Empty socket likely: `-100`
- Socket cover likely: `-60`
- RAM detected: `+35`
- NVMe detected: `+25`

## Reliability

This is a ranking and triage tool, not an unattended purchasing system. Cooler detection should become robust with a labeled dataset and an object detector. Bare CPU and socket-state detection require tighter geometric validation and should retain human review for ambiguous cases.

## Incremental daily operation

The daily runner keeps a committed seven-day rolling ledger at `data/processed.json`. A listing is skipped only when the same ShopGoodwill item ID has already been processed with the same detector code version. The detector version is a SHA-256 fingerprint of the scoring and gallery-extraction source files, so changing detection code automatically causes active listings to be reprocessed.

```bash
python3 src/daily_run.py --query motherboard --pages 3 --retention-days 7
```

After a successful run, publish the updated ledger through the GitHub App:

```bash
./scripts_commit_state.sh
```

The ledger intentionally stores compact scores and metadata rather than images or full per-crop reports. Entries not seen within the retention window are removed. Generated listings, galleries, images, and detailed reports remain under `output/` and are ignored by Git.

## Incremental daily operation

The daily runner keeps a committed seven-day rolling ledger at `data/processed.json`. A listing is skipped only when the same ShopGoodwill item ID has already been processed with the same detector code version. The detector version is a SHA-256 fingerprint of the scoring and gallery-extraction source files, so changing detection code automatically causes active listings to be reprocessed.

```bash
python3 src/daily_run.py --query motherboard --pages 3 --retention-days 7
```

After a successful run, publish the updated ledger through the GitHub App:

```bash
./scripts_commit_state.sh
```

The ledger intentionally stores compact scores and metadata rather than images or full per-crop reports. Entries not seen within the retention window are removed. Generated listings, galleries, images, and detailed reports remain under `output/` and are ignored by Git.

### Change-aware processing

Each ledger entry now records three fingerprints:

- `detector_version`: source hash of the detector and gallery extractor.
- `listing_hash`: stable hash of item metadata and the sorted true-gallery image URLs.
- `result_hash`: stable hash of the compact detection result.

A listing is skipped only when its item ID, detector version, and listing hash all match a prior entry. Adding, removing, or replacing a gallery photo therefore triggers analysis even when the detector code is unchanged. A detector-code change also triggers reanalysis. Result hashes make unchanged outcomes explicit and can be used by reporting or commit automation to suppress no-op result publications.

## Phase 1 crawler reliability

The production crawler now includes:

- Persistent Playwright session state under `output/session/`.
- Exponential backoff with jitter for navigation failures.
- Explicit detection of HTTP 403/429/5xx responses, Cloudflare challenges, access-denied pages, and human-verification pages.
- Per-page and per-listing error reports instead of silent omissions.
- Parallel item-gallery extraction with configurable concurrency.
- Retried, parallel image downloads with `Retry-After` support and content-type validation.
- A consolidated `output/run_report.json` for each daily run.

Useful controls:

```bash
python3 src/daily_run.py \
  --browser-retries 4 \
  --gallery-concurrency 4 \
  --download-workers 8
```

Concurrency should remain conservative. ShopGoodwill throttling or blocking is recorded and retried; the crawler does not attempt to bypass access controls.

## Phase 2 spatial hardware detection

Phase 2 adds a spatial object-detection layer based on Grounding DINO. Unlike the original whole-image CLIP ranking, the detector returns labeled bounding boxes and confidence values for specific motherboard regions.

Supported classes include:

- Intel stock, AMD Wraith, tower, and AIO coolers
- visible CPU, empty Intel/AMD socket, and socket cover
- installed RAM and NVMe SSD
- suspected bent socket pins, burn damage, and cracked PCB

The class vocabulary and thresholds are versioned in `config/detection_classes.json`. The inference engine performs per-class non-maximum suppression, aggregates evidence across all listing photos, applies conservative confidence gates, marks ambiguous or damaged listings for human review, and writes annotated images.

```bash
python3 src/build_local_manifest.py \
  --galleries output/pending_galleries.json \
  --cache-dir output/cache/<detector-version> \
  --output output/phase2_manifest.json

python3 src/phase2_detector.py \
  --manifest output/phase2_manifest.json \
  --output output/phase2_report.json \
  --annotated-dir output/annotated
```

This is a production inference framework, but its default zero-shot model still needs validation against a labeled ShopGoodwill dataset before purchasing decisions should be automatic. The confidence gates deliberately route borderline socket and damage cases to review.

### Daily Phase 2 integration

The spatial detector is now part of the normal daily pipeline. The default `--phase2 on` mode runs both detectors, uses the Phase 2 spatial result as the primary result, retains the legacy CLIP score for comparison, and flags disagreements for human review.

```bash
python3 src/daily_run.py --phase2 on
```

Alternative modes:

- `--phase2 off`: legacy CLIP detector only.
- `--phase2 only`: spatial detector only; images are downloaded without running legacy inference.

The detector-version fingerprint now includes the Phase 2 source, class configuration, and model orchestration code. Changing any Phase 2 detector logic or class thresholds therefore causes active listings to be reprocessed. Annotated images are written under `output/annotated/`, and the merged results used by the rolling ledger are written to `output/new_worker_value_report.json`.

## Phase 3 expected-value ranking

Phase 3 replaces the raw detector score as the shopping decision layer with a configurable expected-value model.

The value engine combines:

- current bid and shipping parsed from listing metadata
- optional buyer premium
- estimated motherboard, CPU, cooler, RAM, and NVMe value
- premium-chipset adjustments
- repair and uncertainty risk costs
- target profit and target ROI
- detection confidence

It produces:

- acquisition cost
- estimated gross component value
- repair-risk adjustment
- expected net value and profit
- expected ROI
- recommended maximum bid
- `bid`, `pass`, or `review` recommendation

All assumptions are versioned in `config/value_model.json` rather than embedded in code. The normal daily run now writes `output/value_report.json`, sorted by recommendation, expected profit, and confidence.

```bash
python3 src/value_engine.py \
  --listings output/pending_listings.json \
  --results output/new_worker_value_report.json \
  --model config/value_model.json \
  --output output/value_report.json
```

The default component values are intentionally conservative placeholders. They should be calibrated from actual purchase outcomes and current resale data before treating maximum bids as authoritative.
