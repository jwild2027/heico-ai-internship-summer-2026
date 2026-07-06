# TRACE-Net Route Dispatch Warning Triage v1

`trace_net_route_dispatch_warning_triage_v1` reads the route dispatch coverage audit and turns remaining non-blocking dispatch warnings into explicit cleanup buckets.

It is intentionally read-only. It does not grant answer permission, prove claims, mutate source truth, or write to Postgres, Qdrant, or OpenSearch.

## Inputs

- `trace_net_route_dispatch_coverage_audit_v1.json`

## Outputs

- `trace_net_route_dispatch_warning_triage_v1.json`
- `trace_net_route_dispatch_warning_triage_v1_quality.json`
- `trace_net_route_dispatch_warning_triage_v1_summary.json`

## Triage families

- `blank_candidate_heavy_processing`: blank-candidate pages that still have table/image/OCR/retrieval artifact evidence.
- `ocr_text_dispatch_policy`: OCR/text artifacts on pages without explicit normal-text dispatch.
- `retrieval_answer_legacy_overlap`: legacy answer/retrieval artifacts on pages without explicit normal-text dispatch.
- `unclassified_route_dispatch_warning`: warnings that need a new policy bucket.

## Example

```bash
PYTHONPATH=. python scripts/build_trace_net_route_dispatch_warning_triage_v1.py \
  --route-dispatch-coverage-audit local_data/organization/trace_net/route_dispatch_coverage_audit/trace_net_route_dispatch_coverage_audit_v1.json \
  --output-dir local_data/organization/trace_net/route_dispatch_warning_triage \
  --min-warning-triage-cards 1 \
  --max-unsafe-triage-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-route-dispatch-coverage-audit-quality-pass \
  --require-no-answer-permission \
  --quality
```
