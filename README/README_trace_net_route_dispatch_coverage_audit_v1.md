# TRACE-Net Route Dispatch Coverage Audit v1

`trace_net_route_dispatch_coverage_audit_v1` audits whether existing TRACE-Net page evidence is aligned with the route dispatch manifest.

It reads:

- `route_dispatch_manifest/trace_net_route_dispatch_manifest_v1.json`
- `artifact_detector/trace_net_artifact_detector_v1.json`

It outputs one coverage card per page and reports:

- table evidence on pages where table processing was not allowed
- image/visual evidence on pages where image processing was not allowed
- OCR/text evidence without explicit text dispatch as advisory warnings
- blank-candidate pages that already have heavy processing evidence
- review-required and multi-route dispatch pages

The artifact is advisory and read-only. It does not grant answer permission, does not prove claims, does not mutate source truth, and does not write to Postgres, Qdrant, or OpenSearch.

## Build

```bash
PYTHONPATH=. python scripts/build_trace_net_route_dispatch_coverage_audit_v1.py \
  --route-dispatch-manifest local_data/organization/trace_net/route_dispatch_manifest/trace_net_route_dispatch_manifest_v1.json \
  --artifact-detector local_data/organization/trace_net/artifact_detector/trace_net_artifact_detector_v1.json \
  --output-dir local_data/organization/trace_net/route_dispatch_coverage_audit \
  --min-dispatch-coverage-cards 500 \
  --min-audited-page-artifact-cards 1 \
  --max-unsafe-audit-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-route-dispatch-manifest-quality-pass \
  --require-artifact-detector-quality-pass \
  --require-no-answer-permission \
  --quality
```

## Quality

```bash
PYTHONPATH=. python scripts/check_trace_net_route_dispatch_coverage_audit_v1_quality.py \
  --report-path local_data/organization/trace_net/route_dispatch_coverage_audit/trace_net_route_dispatch_coverage_audit_v1.json \
  --min-dispatch-coverage-cards 500 \
  --min-audited-page-artifact-cards 1 \
  --max-unsafe-audit-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-route-dispatch-manifest-quality-pass \
  --require-artifact-detector-quality-pass \
  --require-no-answer-permission \
  --write-json
```
