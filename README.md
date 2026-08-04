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

## Phase 4 model identification and market calibration

Phase 4 adds model-specific valuation and confidence intervals.

The daily pipeline now:

1. Extracts motherboard and CPU model candidates from listing titles, descriptions, and OCR of cached images.
2. Fuzzy-matches candidates against a versioned market catalog.
3. Resolves low/median/high market values from either the catalog or at least three matching real purchase outcomes.
4. Enriches the Phase 3 report with market-value, profit, and maximum-bid intervals.
5. Writes `output/phase4_value_report.json`.

New files:

- `config/market_values.json`: maintainable model-level price ranges.
- `data/purchase_outcomes.json`: committed history of actual purchases and realized values.
- `src/model_identification.py`: title/OCR extraction and catalog matching.
- `src/market_pricing.py`: catalog and empirical pricing resolution.
- `src/outcome_tracker.py`: records actual results for calibration.
- `src/phase4_enrichment.py`: confidence-interval enrichment.

Record an actual outcome with:

```bash
python3 src/outcome_tracker.py \
  --item-id 123456789 \
  --component-type cpu \
  --model "INTEL CORE I7-9700K" \
  --purchase-cost 65 \
  --realized-value 125
```

The bundled prices are seed values, not live market claims. Daily reliability improves as the catalog is maintained and actual outcomes accumulate.

## Phase 5 supervised learning and active learning

Phase 5 adds the infrastructure required to replace zero-shot inference with a dedicated, measurable detector.

It includes:

- a versioned bounding-box annotation store
- an active-learning queue that prioritizes uncertainty, detector disagreement, and unknown models
- deterministic train/validation/test splits
- YOLO-format dataset generation
- Ultralytics training and test evaluation entrypoints
- explicit promotion thresholds for mAP50, precision, and recall
- a model registry with SHA-256 verification and promotion safeguards

Typical workflow:

```bash
python3 src/build_review_queue.py \
  --results output/phase4_value_report.json \
  --output output/review_queue.json

python3 src/annotation_store.py add-box \
  --path output/cache/<version>/<item>_1.jpg \
  --item-id <item> \
  --label cpu_installed \
  --box 100 120 400 420 \
  --reviewer jason

python3 src/dataset_builder.py \
  --output data/training/current

python3 src/train_detector.py \
  --dataset data/training/current/dataset.yaml

python3 src/evaluate_detector.py \
  --weights models/runs/<run>/weights/best.pt \
  --dataset data/training/current/dataset.yaml \
  --output models/runs/<run>/evaluation.json

python3 src/model_registry.py register \
  --name <run> \
  --weights models/runs/<run>/weights/best.pt \
  --evaluation models/runs/<run>/evaluation.json

python3 src/model_registry.py promote --name <run>
```

The framework does not claim a trained production model until enough images have been labeled and a candidate passes the configured test thresholds. This prevents a model from becoming active merely because training completed.

## Phase 6 production deployment, canarying, and drift monitoring

Phase 6 connects promoted Phase 5 models to the daily pipeline without removing the validated zero-shot fallback.

The production router supports:

- `auto`: deterministic canary routing according to `canary_fraction`
- `trained`: route every listing through the active registered model
- `fallback`: disable trained inference immediately

If no model is promoted, or trained inference raises an error, the pipeline uses the Phase 2 result and records the fallback reason. Daily output includes the backend and model used for every listing.

The monitoring layer tracks mean confidence, review rate, and CPU-state frequency. It compares current inference against a committed baseline and reports confidence drops, review-rate spikes, and class-frequency shifts. `src/rollback_model.py` provides an explicit emergency return to fallback mode.

Configuration is stored in `config/deployment.json`; the baseline is stored in `data/monitoring/baseline.json`.

```bash
python3 src/daily_run.py --production-model auto
python3 src/rollback_model.py --reason "confidence drift"
```

A trained model is still not used until Phase 5 registers and promotes one. This makes deployment safe before the first production-quality trained model exists.

### Phase 6 hardening

Production deployment now verifies the SHA-256 of the active model before inference. Missing or modified weights are rejected and routed to the fallback detector. The daily pipeline always builds the local image manifest, including legacy-only Phase 2 mode, and monitoring drift is reported without terminating an otherwise successful daily run. Drift adds `rollback_recommended` and `rollback_reasons` to `run_report.json`; changing Phase 6 routing, integrity, monitoring, or deployment configuration changes the detector version and reprocesses active listings.

## Phase 7 continual learning and controlled model improvement

Phase 7 closes the learning loop. Newly reviewed images accumulate in the annotation store, and the continual-learning controller determines when there is enough new data to justify another training run. It enforces minimum total labels, minimum newly labeled images, a cooldown between runs, and a failure circuit breaker.

New candidates are registered but not automatically trusted. `compare_models.py` compares a candidate against the active model using relative mAP50, precision, and recall requirements. `continual_promotion.py` requires explicit approval by default because `automatic_promotion` is false.

```bash
python3 src/training_status.py
python3 src/continual_learning.py --dry-run
python3 src/continual_learning.py
python3 src/compare_models.py --candidate <name> --output models/runs/<name>/comparison.json
python3 src/continual_promotion.py --candidate <name> --comparison models/runs/<name>/comparison.json
```

Configuration and persistent state are stored in `config/continual_learning.json` and `data/continual/state.json`. This creates a repeatable active-learning cycle without allowing a newly trained model to silently replace production inference.
