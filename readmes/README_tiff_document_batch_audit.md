# TIFF document batch intake audit

Adds a read-only command-line audit for a larger or messier TIFF/ResCarta folder before it is pointed at the backend pipeline.

It does not OCR, rename, move, index, or mutate files. It only reports the shape of the folder:

- TIFF count
- OCR text count
- metadata count
- duplicate names/stems
- obvious TIFF/OCR pairing gaps
- top-level folder distribution
- likely ResCarta `pages/` + `ocr/` layout
- JSON output when requested

Example:

```bash
python scripts/audit_document_batch.py --root local_data/rescarta_exports --write-json
```

For a future messy folder:

```bash
python scripts/audit_document_batch.py --root /path/to/messy/folder --max-files 50000 --write-json
```
