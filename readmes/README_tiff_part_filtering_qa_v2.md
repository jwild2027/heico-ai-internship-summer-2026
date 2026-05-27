# TIFF Part Filtering / QA v2

This patch tightens the part-catalog QA layer after the first filtered rebuild.

## Why this patch exists

The rebuild reduced noisy part mentions, but the QA report still surfaced values such as:

```text
25-21-00-46
25-21-00-105
25-IPL
T.P
IGURE
SHEET
```

Those are useful OCR/search references, but they are not aircraft catalog part numbers or useful nomenclature names. They should not appear as high-priority missing-nomenclature or nomenclature-group QA defects.

## What changed

- Strengthened `tiff/part_filters.py`.
- Updated `tiff/part_qa.py` to suppress ATA/figure/manual references from the main QA report.
- Added `--include-info-noise` to `scripts/report_part_catalog_qa.py` for optional debug rows.
- Added `scripts/report_non_part_reference_mentions.py` for suppressed-reference review.
- Added unit tests for the noisy values seen in the real report.

## Main command

```bash
python scripts/report_part_catalog_qa.py --config local_config.yaml
```

## Optional debug command

```bash
python scripts/report_non_part_reference_mentions.py --config local_config.yaml --limit 100
```

## Expected effect

The main QA report should focus more on real catalog issues:

- real part numbers with conflicting cleaned names;
- real part numbers missing nomenclature;
- suspicious ATA mismatches for real parts;
- useful nomenclature groups such as `HOLDER, MAGAZINE`.

ATA references like `25-21-00-46` should move out of the main QA report.
