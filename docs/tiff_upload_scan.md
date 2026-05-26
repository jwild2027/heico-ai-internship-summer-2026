# TIFF Upload Scan

This adds a small upload workflow for one TIFF at a time.

## Streamlit UI

```bash
streamlit run tiff_upload_scan.py
```

The UI will:

1. Accept one `.tif` or `.tiff` file.
2. Save it under `local_data/uploads/`.
3. Scan file metadata and TIFF technical metadata.
4. Parse first-pass drawing metadata from the filename.
5. Write a JSON report under `local_data/json_scans/`.
6. Offer the JSON as a download.

## CLI

```bash
python scripts/scan_tiff_to_json.py --input path/to/file.tif --output local_data/json_scans/file.scan.json --print
```

For faster scans of very large TIFFs:

```bash
python scripts/scan_tiff_to_json.py --input path/to/file.tif --output local_data/json_scans/file.scan.json --no-hash
```

## Current scope

This version does not run OCR yet. It produces JSON from:

- file metadata
- TIFF technical metadata
- filename-based drawing metadata parsing

Title-block OCR will be added in the next step.
