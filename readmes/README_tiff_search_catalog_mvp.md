# TIFF Search Catalog MVP

This drop-in patch adds the first local search layer for the TIFF/OCR pipeline.

It builds a SQLite search database from the existing ResCarta staging export:

```text
local_data/rescarta_exports/<manual_id>/
  metadata.json
  manifest.json
  pages/*.tif
  ocr/*.txt
  ocr/*.metadata.json
```

It creates:

```text
local_data/db/tiff_search.db
```

The search database stores searchable OCR text, metadata, extracted part numbers,
and pointers back to the TIFF/OCR files. It does not store TIFF image bytes.

## Main commands

Build the search index:

```bash
python scripts/build_tiff_search_index.py --rescarta-export-dir local_data/rescarta_exports --output-db local_data/db/tiff_search.db
```

Search it:

```bash
python scripts/search_tiffs.py --db-path local_data/db/tiff_search.db "120-50648-533"
```

Open the first matching TIFF with the system viewer:

```bash
python scripts/search_tiffs.py --db-path local_data/db/tiff_search.db "120-50648-533" --open-first
```

Run the unit test:

```bash
python -m pytest tests/unit/test_tiff_search_index.py -q
```
