# TRACE-Net Table OCR BBox Sidecar Generator v1

`trace_net_table_ocr_bbox_sidecar_generator_v1` generates local OCR bounding-box sidecars for resolved table page images.

It is designed to unlock the next table route:

```text
resolved TIFF table page
  -> Tesseract TSV/hOCR-style word boxes
  -> OCR bbox JSONL sidecars
  -> part-number OCR match sidecars
  -> TRACE-Net OCR bbox enrichment
  -> better table-region crops for morphology
```

## Inputs

- `local_data/organization/trace_net/table_image_resolver/trace_net_table_image_resolver_v1.json`
- optional `local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json`
- optional `local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json`
- local resolved TIFF/page images under `--image-root`
- local `tesseract` command, configurable with `--tesseract-cmd`

## Outputs

The module writes under:

```text
local_data/organization/trace_net/table_ocr_bbox_sidecars/
```

Primary artifacts:

- `trace_net_table_ocr_bbox_sidecar_generator_v1.json`
- `trace_net_table_ocr_bbox_sidecar_generator_v1_quality.json`
- `trace_net_table_ocr_bbox_sidecar_generator_v1_summary.json`
- `trace_net_table_ocr_bbox_sidecar_generator_v1_manifest.json`
- `trace_net_table_ocr_bbox_sidecar_generator_v1_cards.jsonl`

Per-page sidecars are written under:

```text
local_data/organization/trace_net/table_ocr_bbox_sidecars/sidecars/
```

For each page/table image, the generator attempts to write:

- `*.tsv` raw Tesseract TSV output
- `*_ocr_bboxes.jsonl` word-level OCR bbox records
- `*_ocr_lines.jsonl` line-level OCR bbox records
- `*_part_number_matches.jsonl` detected and repaired part-number OCR matches
- `*_summary.json` page/table OCR sidecar summary

## Safety contract

This module is advisory only.

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission
- No claim-proof authority
- Generated OCR boxes are crop/routing helpers only

## Build

```bash
python scripts/build_trace_net_table_ocr_bbox_sidecar_generator_v1.py \
  --table-image-resolver local_data/organization/trace_net/table_image_resolver/trace_net_table_image_resolver_v1.json \
  --table-line-geometry local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --image-root . \
  --output-dir local_data/organization/trace_net/table_ocr_bbox_sidecars \
  --tesseract-cmd tesseract \
  --lang eng \
  --psm 6 \
  --max-pages 20 \
  --min-source-cards 1 \
  --min-attempted-pages 1 \
  --min-generated-sidecar-pages 1 \
  --min-ocr-word-records 1 \
  --min-part-number-matches 1 \
  --max-unsafe-sidecar-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-table-image-resolver-quality-pass \
  --require-no-answer-permission \
  --require-tesseract-available \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_table_ocr_bbox_sidecar_generator_v1_quality.py \
  --report-path local_data/organization/trace_net/table_ocr_bbox_sidecars/trace_net_table_ocr_bbox_sidecar_generator_v1.json \
  --min-source-cards 1 \
  --min-attempted-pages 1 \
  --min-generated-sidecar-pages 1 \
  --min-ocr-word-records 1 \
  --min-part-number-matches 1 \
  --max-unsafe-sidecar-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-table-image-resolver-quality-pass \
  --require-no-answer-permission \
  --require-tesseract-available \
  --write-json
```

## Notes

If Tesseract is not on PATH, pass an explicit command path:

```bash
--tesseract-cmd "/c/Program Files/Tesseract-OCR/tesseract.exe"
```

If the command returns no OCR words, try another page segmentation mode, such as:

```bash
--psm 4
```

The generator includes split-token repair for part numbers such as `120-1 7588-001` -> `120-17588-001` when adjacent OCR words can be joined safely.
