# TIFF changed-file bridge

This script bridges Stage 0 inventory and Stage 1 OCR/metadata scanning.

Stage 0 produces an inventory DB:

```text
scripts/tiff_inventory_hash_crawler.py
  -> source_files
  -> tiff_pages.change_status
```

The bridge script reads that inventory DB and writes a list of TIFF files that have at least one page marked `new` or `changed`.

## Command

```bash
python scripts/list_changed_tiffs_for_scan.py \
  --inventory-db local_data/db/tiff_inventory_hashes_full.db \
  --output local_data/changed_tiffs.txt
```

After a second crawl with no file changes, the output file should be empty:

```text
Changed/new TIFF files: 0
```

## Relative paths

```bash
python scripts/list_changed_tiffs_for_scan.py \
  --inventory-db local_data/db/tiff_inventory_hashes_full.db \
  --output local_data/changed_tiffs_relative.txt \
  --relative
```

## JSON output

```bash
python scripts/list_changed_tiffs_for_scan.py \
  --inventory-db local_data/db/tiff_inventory_hashes_full.db \
  --output local_data/changed_tiffs.json \
  --json
```

## Why this matters

For the eventual large TIFF server, the full workflow should be:

```text
Inventory crawler finds new/changed pages
  -> bridge writes changed_tiffs.txt
  -> OCR/metadata scanner processes only those files
```

This avoids OCRing an entire large server on every run.
