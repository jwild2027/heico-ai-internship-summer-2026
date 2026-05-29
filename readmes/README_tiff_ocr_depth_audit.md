# TIFF OCR Depth Audit

This patch adds a read-only OCR depth audit. It checks whether existing OCR text
looks like useful full-page OCR or only missing/empty/header-only text.

## Why this matters

If the source server only has header OCR, then PostgreSQL graph extraction,
OpenSearch keyword search, Qdrant vectors, RAG, and AI page context all need a
controlled full-page OCR pipeline before production indexing.

## Run against current organization export

```bash
python scripts/audit_ocr_depth.py --write-json
```

## Run against the raw public TIFF ZIP

```bash
python scripts/audit_ocr_depth.py --zip /c/Users/juswil/Documents/00000027/metadata.zip --write-json
```

## Run against a future real server folder

```bash
python scripts/audit_ocr_depth.py --root /path/to/tiff/server/root --max-pages 100000 --write-json
```

## Classifications

- `missing_ocr`
- `empty_ocr`
- `short_ocr`
- `header_only_ocr`
- `full_page_ocr_likely`
- `noisy_ocr`
- `unreadable_ocr`

The audit does not run OCR and does not modify any pipeline data.
