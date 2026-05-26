# TIFF Inventory Hash Crawler

This is the **Stage 0** crawler for large TIFF folders.

It does not replace the TIFF OCR/classification/manual grouping pipeline. It runs before that pipeline and answers:

- What TIFF files exist?
- Which files/pages are new, changed, or unchanged?
- Which pages are exact duplicates?
- Which files failed to read?
- Which files disappeared from the source folder?

## Recommended first test

Run on a small limit first:

```bash
python scripts/tiff_inventory_hash_crawler.py \
  --root local_data/sample_tiffs \
  --db local_data/db/tiff_inventory_hashes.db \
  --limit-files 10
```

Run the same command a second time. The first run should show pages as `new`; the second should show them as `unchanged`.

## Summary

```bash
python scripts/summarize_tiff_inventory_db.py \
  --db local_data/db/tiff_inventory_hashes.db
```

## Quick mode

For a very large server, full SHA-256 file hashing can be expensive. Quick mode avoids reading every byte for file hashing, but still opens the TIFF to hash page pixels.

```bash
python scripts/tiff_inventory_hash_crawler.py \
  --root local_data/sample_tiffs \
  --db local_data/db/tiff_inventory_hashes_quick.db \
  --no-file-hash
```

## Missing file detection

```bash
python scripts/tiff_inventory_hash_crawler.py \
  --root local_data/sample_tiffs \
  --db local_data/db/tiff_inventory_hashes.db \
  --mark-missing
```

## OCR

The crawler has optional full-page OCR, but leave it off for now. The existing TIFF scanner is better for document metadata because it uses region-based OCR and the tuned manual/drawing parsers.

If OCR is used, pass the local Tesseract path:

```bash
python scripts/tiff_inventory_hash_crawler.py \
  --root local_data/sample_tiffs \
  --db local_data/db/tiff_inventory_hashes_ocr.db \
  --ocr \
  --tesseract-cmd 'C:\Users\juswil\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
```

## Pipeline placement

```text
Stage 0: TIFF inventory/hash crawler
  raw TIFF server
  -> file hash / quick fingerprint
  -> page pixel hash
  -> dHash near-duplicate hash
  -> new/changed/unchanged detection
  -> inventory SQLite DB

Stage 1: Metadata scanner
  new/changed TIFFs
  -> title/header OCR
  -> document type classification
  -> manual/drawing metadata
  -> scan SQLite DB

Stage 2: Manual grouping
  scanned pages
  -> logical manual objects

Stage 3: ResCarta
  grouped manual
  -> staging package
  -> ResCarta archive/viewer

Stage 4: RAG
  OCR/metadata
  -> search/vector index
  -> local LLM
  -> ResCarta citations
```
