# TRACE-Net OpenSearch Loader Smoke v1

`trace_net_opensearch_loader_smoke_v1` validates that the already-built TRACE-Net OpenSearch Adapter v1 artifact is ready for exact-search load handoff.

This is a dry-run/local smoke by default. It reads the OpenSearch Adapter JSON, checks document lineage and mapping readiness, creates a small bulk-load preview, and writes exact-search query plans for part-number, OCR phrase, and table-cell queries.

## Inputs

- `local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json`

## Outputs

- `local_data/organization/trace_net/opensearch_loader_smoke/trace_net_opensearch_loader_smoke_v1.json`
- `local_data/organization/trace_net/opensearch_loader_smoke/trace_net_opensearch_loader_smoke_v1_quality.json`
- `local_data/organization/trace_net/opensearch_loader_smoke/trace_net_opensearch_loader_smoke_v1.md`
- `local_data/organization/trace_net/opensearch_loader_smoke/trace_net_opensearch_loader_smoke_v1_bulk_preview.ndjson`

## Safety contract

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- Query plans are retrieval-only and cannot prove claims.

## Build

```bash
python scripts/build_trace_net_opensearch_loader_smoke_v1.py \
  --opensearch-adapter local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json \
  --output-dir local_data/organization/trace_net/opensearch_loader_smoke \
  --index-name trace_net_safe_search_v1 \
  --min-documents 100 \
  --min-page-scoped-documents 100 \
  --min-query-plans 3 \
  --require-mapping \
  --require-adapter-quality-pass \
  --require-bulk-preview \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_opensearch_loader_smoke_v1_quality.py \
  --report-path local_data/organization/trace_net/opensearch_loader_smoke/trace_net_opensearch_loader_smoke_v1.json \
  --min-documents 100 \
  --min-page-scoped-documents 100 \
  --min-query-plans 3 \
  --require-mapping \
  --require-adapter-quality-pass \
  --require-bulk-preview \
  --write-json
```

## Expected safety counters

```text
quality_status: PASS
missing_page_id_count: 0
missing_source_trace_count: 0
unsafe_index_document_count: 0
raw_feedback_indexed_count: 0
raw_visual_output_indexed_count: 0
raw_ocr_unfiltered_indexed_count: 0
retrieval_only_answer_allowed_count: 0
source_truth_mutation_allowed_count: 0
postgres_write_attempt_count: 0
qdrant_write_attempt_count: 0
opensearch_write_attempt_count: 0
```
