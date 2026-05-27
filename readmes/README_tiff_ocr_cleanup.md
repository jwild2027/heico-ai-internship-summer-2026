# TIFF OCR Cleanup and Canonical Part Names

This add-on adds a cleanup layer before the part catalog and RAG steps.

It keeps the raw OCR text in `pages.ocr_text` unchanged, then creates cleaned derivative tables in the same SQLite database:

```text
ocr_clean_pages
part_catalog_mentions_clean
part_catalog_clean
```

## Why this exists

Raw OCR from IPL pages can contain dot leaders, footer text, title-block labels, and effectivity artifacts such as:

```text
HOLDER, MAGAZINE........0..0..:EEEE WS4956
HOLDER, MAGAZINE... VWS4956
```

The cleaned/canonical result should be:

```text
HOLDER, MAGAZINE
```

This makes the search UI and RAG answers cleaner.

## Recommended rebuild order

Run this after building `tiff_search.db`:

```bash
python scripts/build_tiff_search_index.py --rescarta-export-dir local_data/rescarta_exports --output-db local_data/db/tiff_search.db
python scripts/rebuild_clean_part_catalog.py --db-path local_data/db/tiff_search.db
python scripts/build_rag_chunks.py --db-path local_data/db/tiff_search.db
python scripts/build_rag_embeddings.py --db-path local_data/db/tiff_search.db --model bge-m3:latest
```

Then ask:

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model llama3.1:8b "What is part number 120-37313-001?"
```

Expected cleaner answer:

```text
120-37313-001 is listed as HOLDER, MAGAZINE.
```

## New scripts

```text
scripts/clean_tiff_ocr.py
scripts/rebuild_clean_part_catalog.py
scripts/report_ocr_cleanup.py
```

## Updated modules

```text
tiff/ocr_cleanup.py
tiff/part_catalog.py
tiff/search_index.py
tiff/rag_chunks.py
tiff/rag_retriever.py
tiff/rag_answer.py
```

## Important note

This is post-OCR cleanup. It does not rerun Tesseract, and it does not delete raw OCR. The system keeps raw OCR for audit and source review, while downstream catalog/RAG uses cleaned derivatives when available.
