# TRACE-Net OpenSearch Missing Lineage Inspector v1

Focused diagnostic module for the current OpenSearch Adapter v1 lineage blocker.

## Purpose

Reads the local OpenSearch Adapter v1 artifact and writes a diagnostic report that lists every document missing page/source lineage.

This is intended to make the next adapter fix narrow and safe: inspect only the missing-lineage documents, patch the adapter source that produced them, then rebuild until missing lineage is zero.

## Inputs

- `local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json`

## Outputs

- `local_data/organization/trace_net/opensearch_missing_lineage_inspector/trace_net_opensearch_missing_lineage_inspector_v1.json`
- `local_data/organization/trace_net/opensearch_missing_lineage_inspector/trace_net_opensearch_missing_lineage_inspector_v1_quality.json`
- `local_data/organization/trace_net/opensearch_missing_lineage_inspector/trace_net_opensearch_missing_lineage_inspector_v1.md`

## Safety contract

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- No claim-proof authority.

## Current expected use

Before the OpenSearch Adapter lineage fix, run with:

```bash
python scripts/build_trace_net_opensearch_missing_lineage_inspector_v1.py \
  --opensearch-adapter local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json \
  --output-dir local_data/organization/trace_net/opensearch_missing_lineage_inspector \
  --min-documents 100 \
  --max-missing-lineage-docs 6 \
  --quality
```

After the adapter lineage fix, rerun with:

```bash
python scripts/check_trace_net_opensearch_missing_lineage_inspector_v1_quality.py \
  --report-path local_data/organization/trace_net/opensearch_missing_lineage_inspector/trace_net_opensearch_missing_lineage_inspector_v1.json \
  --min-documents 100 \
  --max-missing-lineage-docs 0 \
  --write-json
```
