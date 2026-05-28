# TIFF OCR coverage audit

Adds a read-only command-line audit for OCR text coverage across source-linked pages.

It checks:

- source-linked page count
- missing OCR paths
- missing OCR files
- unreadable OCR files
- empty OCR files
- suspiciously short OCR files
- sample rows with TIFF/OCR/ResCarta pointers

Example:

```bash
python scripts/audit_ocr_coverage.py --config local_config.yaml --write-json
```

Strict mode fails only when OCR paths/files are missing or unreadable:

```bash
python scripts/audit_ocr_coverage.py --config local_config.yaml --strict
```

To make empty/short OCR files fail the command too:

```bash
python scripts/audit_ocr_coverage.py --config local_config.yaml --fail-on-empty-ocr
```

Empty OCR is not fatal by default because some scanned pages are blank separators/covers. Inspect the samples before deciding whether to regenerate OCR or suppress those pages.
