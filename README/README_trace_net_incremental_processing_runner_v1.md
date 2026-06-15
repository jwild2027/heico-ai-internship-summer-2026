# TRACE-Net Incremental Processing Runner v1

This module turns a TRACE-Net Incremental Orchestrator v1 report into a server-ready dry-run processing plan.

It is the first execution layer after:

```text
Step 24: Incremental Corpus Manifest
Step 25: Incremental Orchestrator
Step 25.1: Incremental Processing Runner
```

The runner is intentionally plan-only. It does not run OCR, embeddings, Qdrant writes, OpenSearch writes, Postgres writes, graph writebacks, or source-truth mutations.

## Safety contract

Every processing step has:

```text
external_command_executed = false
postgres_write_attempted = false
qdrant_write_attempted = false
opensearch_write_attempted = false
source_truth_mutation_allowed = false
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
```

## Clean manifest run

```bash
python scripts/run_trace_net_incremental_processing_v1.py \
  --orchestrator-report local_data/organization/trace_net/incremental_orchestrator/trace_net_incremental_orchestrator_v1.json \
  --output-dir local_data/organization/trace_net/incremental_processing_runner \
  --execution-mode dry-run \
  --require-page-count 509 \
  --require-no-full-rescan \
  --max-unchanged-page-reprocess 0 \
  --quality
```

Expected when no files changed:

```text
planned_job_count: 0
processing_step_count: 0
no_op_processed: True
full_rescan_required: False
unchanged_page_reprocess_count: 0
```

## Dirty manifest run

If you previously built a dirty orchestrator from the first baseline manifest, run:

```bash
python scripts/run_trace_net_incremental_processing_v1.py \
  --orchestrator-report local_data/organization/trace_net/incremental_orchestrator_dirty/trace_net_incremental_orchestrator_v1.json \
  --output-dir local_data/organization/trace_net/incremental_processing_runner_dirty \
  --execution-mode dry-run \
  --batch-size 100 \
  --require-page-count 509 \
  --min-processing-steps 1 \
  --require-no-full-rescan \
  --max-unchanged-page-reprocess 0 \
  --quality
```

Expected when files/pages are dirty:

```text
planned_job_count: >0
processing_step_count: >0
external_command_execution_count: 0
source_truth_mutation_allowed_count: 0
```

## Quality check

```bash
python scripts/check_trace_net_incremental_processing_runner_v1_quality.py \
  --report-path local_data/organization/trace_net/incremental_processing_runner/trace_net_incremental_processing_runner_v1.json \
  --require-page-count 509 \
  --require-no-full-rescan \
  --max-unchanged-page-reprocess 0 \
  --write-json
```

## Output folder

```text
local_data/organization/trace_net/incremental_processing_runner/
```

Generated files:

```text
trace_net_incremental_processing_runner_v1.json
trace_net_incremental_processing_runner_v1_steps.jsonl
trace_net_incremental_processing_runner_v1_batches.jsonl
trace_net_incremental_processing_runner_v1_summary.json
trace_net_incremental_processing_runner_v1_quality.json
trace_net_incremental_processing_runner_v1_manifest.json
trace_net_incremental_processing_runner_v1.md
trace_net_incremental_processing_runner_v1.html
```

## Why this matters

This proves the server-ready incremental contract:

```text
No changes -> no work.
Changed pages -> changed-page work only.
No full rescan.
No writes until a later executor is explicitly enabled and gated.
```
