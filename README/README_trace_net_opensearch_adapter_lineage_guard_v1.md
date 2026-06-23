# TRACE-Net OpenSearch Adapter Lineage Guard v1

This focused patch protects the OpenSearch exact-search path by removing adapter documents that lack page/source lineage before they are passed to Loader Smoke or any future live OpenSearch index.

## Purpose

OpenSearch is intended to be the exact-search channel for part numbers, table cells, OCR phrases, ATA labels, and other identifier-style queries. Exact-search documents must always carry source lineage. A document without a `page_id` or `source_page_ids` is not safe to index because it cannot be resolved back through TRACE-Net source/citation/final-gate logic.

## Inputs

- `local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json`
- Existing adapter source inputs used by the lineage rebuild script.

## Outputs

The guarded rebuild writes the standard OpenSearch Adapter output files back under:

- `local_data/organization/trace_net/opensearch_adapter/`

including the guarded adapter report, documents JSONL, bulk NDJSON preview, summary, quality, manifest, and markdown report.

## Safety contract

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- No claim-proof authority.
- Documents missing page/source lineage are dropped from the exact-search artifact.
