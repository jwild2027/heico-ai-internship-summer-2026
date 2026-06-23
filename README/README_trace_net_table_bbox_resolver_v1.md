# TRACE-Net Table BBox Resolver v1

Read-only table-region bounding-box resolver for TRACE-Net table geometry.

This patch wires the PASS OCR bbox enrichment artifact into the resolver so OCR-derived table/part-number crop candidates can replace low-specificity aggregated boxes when they pass conservative safety gates.

## Inputs

- `local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json`
- `local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json`
- `local_data/organization/trace_net/table_image_resolver/trace_net_table_image_resolver_v1.json`
- optional `local_data/organization/trace_net/table_ocr_bbox_enrichment/trace_net_table_ocr_bbox_enrichment_v1.json`
- local page images under `--image-root`

## Outputs

- `local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json`
- `trace_net_table_bbox_resolver_v1_cards.jsonl`
- `trace_net_table_bbox_resolver_v1_summary.json`
- `trace_net_table_bbox_resolver_v1_quality.json`
- `trace_net_table_bbox_resolver_v1_manifest.json`

## OCR enrichment behavior

The resolver now accepts OCR enrichment crop candidates when:

- `crop_candidate_ready` is true
- `bbox_source` is an OCR enrichment source such as `ocr_part_number_token_match` or `ocr_table_text_token_match`
- `bbox_confidence` is at least 0.72
- enough OCR boxes or part-number boxes matched
- bbox width/height are not tiny
- bbox coverage is not effectively the whole page

Broad OCR crops are allowed but review-flagged as advisory. Full-page-like crops are rejected.

## Safety contract

This module is read-only and advisory. It does not write to Postgres, Qdrant, or OpenSearch. It does not mutate source truth. It does not grant answer permission and cannot prove claims.
