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
