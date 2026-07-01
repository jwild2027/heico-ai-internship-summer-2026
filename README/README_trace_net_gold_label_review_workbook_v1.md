# TRACE-Net Gold Label Review Workbook v1

Builds a 509-page review workbook from the OCR route scan pack and canonical route label taxonomy.

The workbook is for route-label verification only. It has no answer permission, does not mutate source truth, and does not write to Postgres, Qdrant, or OpenSearch.

Inputs:

- `trace_net_ocr_route_scan_pack_v1.json`
- `trace_net_route_label_taxonomy_v1.json`
- optional source package path for traceability

Outputs:

- JSON manifest
- JSONL review rows
- CSV review table
- XLSX workbook with Summary, Gold Review, and Taxonomy sheets
- HTML review table

Reviewers should fill `gold_route_label`, `review_status`, and `review_notes`, then the next module can compare suggested vs gold labels.
