# Document batch audit: empty-file detail

This patch tightens the read-only document batch intake audit.

It keeps the previous behavior and adds detail for zero-byte files:

```text
Empty files: <count>
Empty file types:
  .json: <count>
  .txt: <count>
  .tif: <count>
Issues/warnings:
  - review empty_files ...
      example: path/to/empty/file
```

Why this matters:

- Empty TIFFs can break source-image review.
- Empty OCR text can make pages unsearchable.
- Empty metadata files may be harmless placeholders, but they should be visible before scaling.

Run:

```bash
python scripts/audit_document_batch.py --root local_data/rescarta_exports --write-json
```

For a messy candidate folder:

```bash
python scripts/audit_document_batch.py --root /path/to/messy/folder --max-files 50000 --write-json
```
