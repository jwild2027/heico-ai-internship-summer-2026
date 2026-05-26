# TIFF pipeline start

This starter layer adds TIFF inventory and first-pass metadata parsing without
changing the existing PDF RAG path.

## First command

```bash
python scripts/inventory_tiffs.py --dir "C:/path/to/tiff-folder" --db-path rag.db --limit 100 --parse-filename
```

## What it does

- Finds `.tif` and `.tiff` files.
- Stores file path, name, size, modified time, hash, page count, dimensions, DPI,
  color mode, and compression.
- Optionally tries to parse drawing metadata from filenames.
- Creates new SQLite tables prefixed with `tiff_`.

## What it does not do yet

- It does not OCR title blocks yet.
- It does not create embeddings yet.
- It does not call any external cloud endpoint.
- It does not move or modify the original TIFFs.

## Next step

Add a local title-block OCR script that crops the likely header/title-block area,
runs Tesseract locally, stores text in `tiff_ocr_texts`, and then calls
`parse_title_block_text()` to populate `tiff_drawing_metadata`.
