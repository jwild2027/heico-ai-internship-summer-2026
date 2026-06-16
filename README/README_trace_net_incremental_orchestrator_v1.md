# TRACE-Net Incremental Orchestrator v1

Step 25 turns the Step 24 incremental corpus manifest into a safe, read-only job plan.

It answers:

```text
What changed?
Which pages are affected?
Which pipeline jobs should run?
Which jobs can be skipped?
Is a full rescan required?
```

It does not execute jobs and does not mutate source truth.

## Safety contract

```text
execution_mode = plan_only
writeback_mode = read_only_job_plan
state_commit_after_success_only = true
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
```

The orchestrator can plan:

```text
ocr_changed_pages
page_element_registry_changed_pages
table_understanding_changed_pages
table_cell_normalizer_changed_pages
figure_chart_understanding_changed_pages
visual_ink_layout_changed_pages
evidence_consensus_changed_pages
fishnet_retry_changed_pages
trust_authority_changed_pages
safe_candidates_changed_pages
embedding_changed_candidates
qdrant_upsert_changed_points
opensearch_upsert_changed_docs
graph_attachment_changed_pages
graph_writeback_changed_nodes
leiden_refresh_required
retrieval_regression_smoke_changed_corpus
```

For removed sources it can plan tombstone/delete jobs, still as a plan only.

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_incremental_orchestrator_v1.py \
  tests/unit/test_trace_net_incremental_orchestrator_v1_quality.py \
  tests/unit/test_trace_net_incremental_orchestrator_v1_script_imports.py \
  -q
```

## Build against a clean Step 24 manifest

Use the second manifest from Step 24 when nothing changed:

```bash
python scripts/build_trace_net_incremental_orchestrator_v1.py \
  --manifest local_data/organization/trace_net/incremental_corpus_manifest_next/trace_net_incremental_corpus_manifest_v1.json \
  --output-dir local_data/organization/trace_net/incremental_orchestrator \
  --require-page-count 509 \
  --quality
```

Expected clean-corpus shape:

```text
Quality status: PASS
dirty_page_count: 0
planned_job_count: 0
full_rescan_required: False
unchanged_page_reprocess_count: 0
```

## Build against a dirty first-run manifest

Use this to see the full incremental job plan for the first-run/new-source case:

```bash
python scripts/build_trace_net_incremental_orchestrator_v1.py \
  --manifest local_data/organization/trace_net/incremental_corpus_manifest/trace_net_incremental_corpus_manifest_v1.json \
  --output-dir local_data/organization/trace_net/incremental_orchestrator_dirty \
  --require-page-count 509 \
  --quality
```

Expected dirty-corpus shape:

```text
Quality status: PASS
dirty_page_count: 509
planned_job_count: > 0
full_rescan_required: False
unchanged_page_reprocess_count: 0
```

## Quality check

```bash
python scripts/check_trace_net_incremental_orchestrator_v1_quality.py \
  --report-path local_data/organization/trace_net/incremental_orchestrator/trace_net_incremental_orchestrator_v1.json \
  --require-page-count 509 \
  --max-unchanged-page-reprocess 0 \
  --require-no-full-rescan \
  --write-json
```

## Inspect planned jobs

```bash
python - <<'PY'
import json
from pathlib import Path
from collections import Counter

path = Path("local_data/organization/trace_net/incremental_orchestrator/trace_net_incremental_orchestrator_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))

print("quality_status:", payload["quality_status"])
print("summary:", payload["summary"])
print("job_type_counts:", Counter(j["job_type"] for j in payload["planned_jobs"]))

for job in payload["planned_jobs"][:10]:
    print()
    print("job_id:", job["job_id"])
    print("job_type:", job["job_type"])
    print("family:", job["job_family"])
    print("affected_page_count:", job["affected_page_count"])
    print("priority:", job["priority"])
    print("runner_hint:", job["runner_hint"])
PY
```

## Output files

```text
local_data/organization/trace_net/incremental_orchestrator/trace_net_incremental_orchestrator_v1.json
local_data/organization/trace_net/incremental_orchestrator/trace_net_incremental_orchestrator_v1_jobs.jsonl
local_data/organization/trace_net/incremental_orchestrator/trace_net_incremental_orchestrator_v1_dirty_pages.jsonl
local_data/organization/trace_net/incremental_orchestrator/trace_net_incremental_orchestrator_v1_summary.json
local_data/organization/trace_net/incremental_orchestrator/trace_net_incremental_orchestrator_v1_quality.json
local_data/organization/trace_net/incremental_orchestrator/trace_net_incremental_orchestrator_v1.md
```

## Why this matters for 5 TB

Step 24 tells TRACE-Net what changed.

Step 25 tells TRACE-Net what to rerun.

That prevents a new file from triggering a full 5 TB rescan.
