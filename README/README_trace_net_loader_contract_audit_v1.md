# TRACE-Net Loader Contract Audit v1

Audits dry-run loader plans before any live storage adapter is allowed to write.

## Purpose

`trace_net_loader_contract_audit_v1` reads the dry-run loader planner output and joins it back to the OCR route scan pack to repair missing raw TIFF lineage fields. It then validates the contract for each loader target:

- Postgres graph/source-map records
- Qdrant semantic embedding candidates
- OpenSearch exact/table candidates

The module is intentionally dry-run only. It never writes to Postgres, Qdrant, or OpenSearch.

## Key guarantees

- Every loader record remains source-traceable before live load is allowed.
- Missing `source_member`, `raw_tiff_reference`, or `source_image_sha256` fields block contract readiness.
- Qdrant candidates require validated non-blank evidence.
- OpenSearch candidates require validated table/exact evidence.
- Live writes remain blocked until a separate explicit live-loader patch is introduced.

## Main command

```bash
python scripts/build_trace_net_loader_contract_audit_v1.py \
  --dry-run-loader-planner local_data/organization/trace_net/dry_run_loader_planner/trace_net_dry_run_loader_planner_v1.json \
  --ocr-route-scan-pack local_data/organization/trace_net/ocr_route_scan_pack_tesseract_full/trace_net_ocr_route_scan_pack_v1.json \
  --output-dir local_data/organization/trace_net/loader_contract_audit \
  --quality
```

## Safety contract

No Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, and no answer permission.

## v1 target-plan join fix

This current-state patch also fixes the dry-run loader contract join: target-specific fields such as `evidence_policy`, `embedding_scope`, and `exact_index_scope` are read from the Postgres/Qdrant/OpenSearch dry-run plan records and joined back to the page-level audit record by `page_id` / `page_number` before contract readiness is scored.

Expected contract-ready counts after the fix, using the current 509-page sample run:

```text
postgres_contract_ready_count: 509
qdrant_contract_ready_count: 450
opensearch_contract_ready_count: 282
missing_lineage_count: 0
```
