# Incremental TIFF scan bridge

`list_changed_tiffs_for_scan.py` reads the Stage 0 inventory database and writes a list of TIFF files whose pages are `new` or `changed`.

`scan_changed_tiffs.py` reads that list and runs the existing TIFF JSON/SQLite scanner only for those files.

This gives the local pipeline an incremental mode:

```text
raw TIFF folder
  -> inventory/hash crawler
  -> changed_tiffs.txt
  -> changed-only OCR/metadata scanner
  -> JSON reports + scan SQLite DB
```

## Current no-change case

After a second inventory crawl, unchanged files produce an empty changed list:

```bash
python scripts/list_changed_tiffs_for_scan.py \
  --inventory-db local_data/db/tiff_inventory_hashes_full.db \
  --output local_data/changed_tiffs.txt \
  --print
```

Then:

```bash
python scripts/scan_changed_tiffs.py \
  --file-list local_data/changed_tiffs.txt \
  --output-dir local_data/json_scans_incremental \
  --db-path local_data/db/tiff_scans_incremental.db \
  --ocr \
  --tesseract-cmd 'C:\Users\juswil\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
```

Expected result when there are no changes:

```text
listed=0 attempted=0 succeeded=0 failed=0
```

## Relative path mode

If the changed list was created with `--relative`, pass `--source-root`:

```bash
python scripts/list_changed_tiffs_for_scan.py \
  --inventory-db local_data/db/tiff_inventory_hashes_full.db \
  --output local_data/changed_tiffs_relative.txt \
  --relative

python scripts/scan_changed_tiffs.py \
  --file-list local_data/changed_tiffs_relative.txt \
  --source-root local_data/sample_tiffs \
  --output-dir local_data/json_scans_incremental \
  --db-path local_data/db/tiff_scans_incremental.db \
  --ocr \
  --tesseract-cmd 'C:\Users\juswil\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
```

## Purpose

For a large TIFF server, recurring jobs should not OCR everything every time. The inventory crawler identifies what changed; this bridge processes only those new/changed files.
