# TRACE-Net IT Issue-Origin Test Matrix v1

This module stress-tests the TRACE-Net IT Operations Console with synthetic quality artifacts.

It is meant for backend/IT confidence testing. It answers:

- Can the IT console catch critical safety issues?
- Can it catch warnings from source/OCR/index/incremental layers?
- Can it catch human-review backlogs?
- Are issue origins covered across the TRACE-Net stack?

The matrix is synthetic and read-only. It does not mutate Postgres, Qdrant, OpenSearch, source files, graph truth, or real pipeline artifacts.

## Issue origin categories covered

Examples include:

- source ingest
- OCR text
- page registry / route planning
- table extraction
- visual / diagram / callout processing
- graph integrity
- trust authority
- evidence consensus
- semantic vector / Qdrant
- retrieval
- Leiden communities
- feedback memory
- answer / final gate
- incremental operations
- OpenSearch / keyword search
- LLM advisory boundaries
- security and leakage

## Run

```bash
python scripts/run_trace_net_it_issue_origin_test_matrix_v1.py \
  --output-dir local_data/organization/trace_net/it_issue_origin_test_matrix \
  --min-scenarios 60 \
  --min-origin-categories 15 \
  --quality
```

## Check quality

```bash
python scripts/check_trace_net_it_issue_origin_test_matrix_v1_quality.py \
  --report-path local_data/organization/trace_net/it_issue_origin_test_matrix/trace_net_it_issue_origin_test_matrix_v1.json \
  --min-scenarios 60 \
  --min-origin-categories 15 \
  --write-json
```

Expected result:

```text
Status: PASS
undetected_scenario_count: 0
```

## Safety rule

This module creates fake failures to prove the IT console can see them. It does not create real failures in the TRACE-Net pipeline.
