# TRACE-Net Retrieval Payload Audit v1

Audits the first three verification steps after the OCR/classifier pipeline:

1. Route separation correctness for `blank`, `plain_text`, `table`, and `image` pages.
2. Chunk/source-trace correctness for semantic payload candidates.
3. Qdrant/OpenSearch payload correctness before any live DB write.

This module is dry-run only. It does not write to Postgres, Qdrant, or OpenSearch; does not mutate source truth; and does not grant answer permission.

## Build

```bash
python scripts/build_trace_net_retrieval_payload_audit_v1.py \
  --loader-contract-audit local_data/organization/trace_net/ocr_classifier_rerun_001/loader_contract_audit/trace_net_loader_contract_audit_v1.json \
  --ocr-route-scan-pack local_data/organization/trace_net/ocr_classifier_rerun_001/ocr_route_scan_pack_tesseract_full/trace_net_ocr_route_scan_pack_v1.json \
  --output-dir local_data/organization/trace_net/ocr_classifier_rerun_001/retrieval_payload_audit \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_retrieval_payload_audit_v1_quality.py \
  --report-path local_data/organization/trace_net/ocr_classifier_rerun_001/retrieval_payload_audit/trace_net_retrieval_payload_audit_v1.json \
  --write-json \
  --min-records 509 \
  --min-route-separation-pass 400 \
  --min-qdrant-payloads 400 \
  --min-opensearch-payloads 250 \
  --max-violation-records 0 \
  --require-source-quality-pass \
  --require-no-human-review-required \
  --max-unsafe 0 \
  --require-no-answer-permission \
  --require-no-source-truth-mutation \
  --require-no-write-attempts
```
