# TIFF title-block OCR

The first TIFF scanner only read file/TIFF technical metadata and parsed drawing
fields from the filename. That caused many `null` values when the filename did
not contain the drawing number, part number, revision, title, or classification.

This add-on enables local title-block OCR with Tesseract.

## Run from the Streamlit uploader

```bash
python -m streamlit run tiff_upload_scan.py
```

Upload a `.tif` or `.tiff` file and keep **Run local title-block OCR** checked.
The JSON report will include:

```text
ocr.status
ocr.combined_text
ocr.regions
drawing_metadata
filename_metadata
drawing_metadata_sources
```

## Run from the command line

```bash
python scripts/scan_tiff_to_json.py \
  --input "C:/path/to/sample.tif" \
  --output "local_data/json_scans/sample.scan.json" \
  --ocr \
  --print
```

## Tesseract setup

The OCR code calls the local `tesseract` executable. Check it with:

```bash
tesseract --version
```

If Git Bash cannot find it, either add Tesseract to PATH or pass the executable
path in the Streamlit sidebar / command line:

```bash
python scripts/scan_tiff_to_json.py \
  --input "C:/path/to/sample.tif" \
  --output "local_data/json_scans/sample.scan.json" \
  --ocr \
  --tesseract-cmd "C:/Program Files/Tesseract-OCR/tesseract.exe"
```

## Current crop regions

The scanner OCRs these regions from page 0:

```text
bottom_right_title_block
bottom_strip
top_strip
right_strip
```

This is a starting point. If your drawings place the title block somewhere else,
change `title_block_boxes()` in `tiff/title_block_ocr.py`.

## Why nulls may remain

Null fields can still happen when:

```text
Tesseract is not installed
The title block is outside the current crop regions
The scan is rotated or low quality
The title block uses labels the parser does not recognize yet
The field is not present in the drawing
```

The next improvement is to save crop preview images for debugging and tune the
crop boxes based on your real TIFF template.
