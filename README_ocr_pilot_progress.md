# OCR pilot progress patch

Adds streaming page progress to `scripts/run_ocr_pilot.py`.

Example:

```bash
python scripts/run_ocr_pilot.py \
  --zip "$METADATA_ZIP" \
  --output-dir local_data/ocr/full_509_psm3 \
  --limit 509 \
  --engine tesseract \
  --tesseract-cmd "$TESSERACT_CMD" \
  --lang eng \
  --psm 3 \
  --timeout-seconds 300 \
  --write-json
```

Progress output example:

```text
OCR pilot progress: selected_pages=509 engine=tesseract psm=3 output_dir=local_data/ocr/full_509_psm3
[1/509] zip_page_000001 -> ocr_succeeded class=likely_full_page chars=487 page_time=2s avg=2s eta=17m 4s
[2/509] zip_page_000002 -> ocr_succeeded class=empty_ocr chars=0 page_time=1s avg=2s eta=16m 55s
```

Options:

```text
--no-progress          disables per-page progress
--progress-every N     prints every N pages instead of every page
```

Run the small progress utility tests:

```bash
python -m pytest tests/unit/test_tiff_ocr_pilot_progress.py -q
```
