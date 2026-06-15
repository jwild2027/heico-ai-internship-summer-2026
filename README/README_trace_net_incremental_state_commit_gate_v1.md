# TRACE-Net Incremental State Commit Gate v1

This module is the safety gate after the incremental processing runner.

It decides whether an incremental run is safe to mark as processed.  It does not mutate the file manifest, Postgres, Qdrant, OpenSearch, source files, graph truth, or any source-truth record.

## Purpose

The incremental pipeline should behave like this:

```text
manifest detects changes
-> orchestrator plans changed-page jobs
-> processing runner plans or executes jobs
-> state commit gate decides whether changed files/pages can be marked clean
```

The gate enforces:

```text
No changed-state commit until required jobs have successful evidence.
No commit if any required job failed.
No commit if a full rescan was required.
No commit if unchanged pages would be reprocessed.
No commit if safety/source-truth mutation flags are present.
```

## Apply patch

```bash
unzip -o /c/Users/juswil/Downloads/tracenet_incremental_state_commit_gate_v1_patch.zip -d .
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_incremental_state_commit_gate_v1.py \
  tests/unit/test_trace_net_incremental_state_commit_gate_v1_quality.py \
  tests/unit/test_trace_net_incremental_state_commit_gate_v1_script_imports.py \
  -q
```

Expected:

```text
11 passed
```

## Build gate for the clean no-op runner

```bash
python scripts/build_trace_net_incremental_state_commit_gate_v1.py \
  --processing-runner-report local_data/organization/trace_net/incremental_processing_runner/trace_net_incremental_processing_runner_v1.json \
  --output-dir local_data/organization/trace_net/incremental_state_commit_gate \
  --require-page-count 509 \
  --require-no-full-rescan \
  --max-unchanged-page-reprocess 0 \
  --quality
```

Expected clean result:

```text
Quality status: PASS
state_commit_decision: no_op_no_state_commit_needed
state_commit_required: False
state_commit_allowed: False
state_commit_performed: False
state_commit_write_attempt_count: 0
```

## Build gate for a dirty dry-run runner

If you built a dirty dry-run processing report:

```bash
python scripts/build_trace_net_incremental_state_commit_gate_v1.py \
  --processing-runner-report local_data/organization/trace_net/incremental_processing_runner_dirty/trace_net_incremental_processing_runner_v1.json \
  --output-dir local_data/organization/trace_net/incremental_state_commit_gate_dirty \
  --require-page-count 509 \
  --require-no-full-rescan \
  --max-unchanged-page-reprocess 0 \
  --require-commit-blocked-for-pending \
  --quality
```

Expected dirty dry-run result:

```text
Quality status: PASS
state_commit_decision: state_commit_pending_execution
state_commit_required: True
state_commit_allowed: False
pending_execution_step_count: >0
state_commit_performed: False
```

This is correct.  Dry-run work should not mark changed files as clean.

## Run quality separately

```bash
python scripts/check_trace_net_incremental_state_commit_gate_v1_quality.py \
  --report-path local_data/organization/trace_net/incremental_state_commit_gate/trace_net_incremental_state_commit_gate_v1.json \
  --require-page-count 509 \
  --require-no-full-rescan \
  --max-unchanged-page-reprocess 0 \
  --write-json
```

## Inspect result

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("local_data/organization/trace_net/incremental_state_commit_gate/trace_net_incremental_state_commit_gate_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))

print("quality_status:", payload["quality_status"])
print("summary:", payload["summary"])

for check in payload["commit_checks"][:20]:
    print()
    print("job_type:", check["job_type"])
    print("execution_status:", check["execution_status"])
    print("commit_check_status:", check["commit_check_status"])
    print("state_commit_allowed_for_step:", check["state_commit_allowed_for_step"])
    print("reason:", check["state_commit_block_reason"])
PY
```

## Output files

```text
local_data/organization/trace_net/incremental_state_commit_gate/
  trace_net_incremental_state_commit_gate_v1.json
  trace_net_incremental_state_commit_gate_v1_checks.jsonl
  trace_net_incremental_state_commit_gate_v1_summary.json
  trace_net_incremental_state_commit_gate_v1_quality.json
  trace_net_incremental_state_commit_gate_v1_manifest.json
  trace_net_incremental_state_commit_gate_v1.md
  trace_net_incremental_state_commit_gate_v1.html
```

## Safety contract

This module is dry-run only:

```text
state_commit_performed = false
state_commit_write_attempt_count = 0
source_truth_mutation_allowed_count = 0
can_answer_directly = false
can_prove_claims = false
```

It is the last safety check before a future state-commit executor marks new/changed files as clean.
