# TRACE-Net Artifact Dependency Registry v1 helper/legacy normalization

This patch tightens the artifact dependency registry before the dirty-planner layer.

## Changes

- Excludes helper/report files from primary artifact records, including:
  - `trace_net_core_algorithm_matrix_v1.json`
- Treats selected legacy files as canonical stage artifacts even when they use older names:
  - `evidence_consensus_summary.json` -> `evidence_consensus`
  - `page_image_recognition_quality.json` -> `image_recognition_quality`
  - `trace_net_qdrant_loader_v1_summary.json` / quality -> `qdrant_loader`
  - `trace_net_evidence_snippet_claims_v1_summary.json` / quality -> `evidence_snippet_claims`
- Uses `status=OK` or `status=PASS` as a quality-status fallback for legacy artifacts that do not have a modern `quality_status` field.
- Tracks optional missing dependencies separately so they do not create noisy hard-missing dependency counts.

## Why

The registry should represent real pipeline stage artifacts, not supplemental helper reports. It also needs to understand older artifact naming so stages like `evidence_consensus` can satisfy dependencies.

## Expected after rebuild

```text
dependency_cycle_count: 0
missing_quality_status_count: 0
quality_not_pass_count: 0
registry_state_counts.scan_error: 0
```

`missing_dependency_reference_count` should drop, ideally to zero. Optional missing references, if any, are reported under `optional_missing_dependency_reference_count`.
