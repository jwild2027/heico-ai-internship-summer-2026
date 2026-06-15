# TRACE-Net Promotion Writeback Dry Run v1

This module turns approved Human Review Promotion Gate records into a **read-only writeback plan**.

It does not mutate:

- Postgres
- Qdrant
- OpenSearch
- graph truth
- source truth
- citations
- trust records
- final answers

It only writes local planning artifacts under:

```text
local_data/organization/trace_net/promotion_writeback_dry_run/
```

## Why it exists

A human review decision is only a recommendation. The Promotion Gate evaluates whether the recommendation is safe. This module is the next boundary: it turns approved promotion evaluations into planned writeback actions, but still performs no writes.

Flow:

```text
Human Review Decision
-> Human Review Promotion Gate
-> Promotion Writeback Dry Run
-> future writeback executor / regression gate
```

## Apply patch

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026

unzip -o /c/Users/juswil/Downloads/tracenet_promotion_writeback_dry_run_v1_patch.zip -d .
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_promotion_writeback_dry_run_v1.py \
  tests/unit/test_trace_net_promotion_writeback_dry_run_v1_quality.py \
  tests/unit/test_trace_net_promotion_writeback_dry_run_v1_script_imports.py \
  -q
```

## Build with current decisions

Your current promotion gate may have zero approved promotion candidates. That is okay. Use `--min-writeback-plans 0`.

```bash
python scripts/build_trace_net_promotion_writeback_dry_run_v1.py \
  --promotion-gate local_data/organization/trace_net/human_review_promotion_gate/trace_net_human_review_promotion_gate_v1.json \
  --review-decisions local_data/organization/trace_net/human_review_decisions/trace_net_human_review_decisions_v1.json \
  --triage-report local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.json \
  --output-dir local_data/organization/trace_net/promotion_writeback_dry_run \
  --min-writeback-plans 0 \
  --require-promotion-gate-quality-pass \
  --quality
```

Expected no-op shape when there are no approved promotions:

```text
TRACE-Net promotion writeback dry run v1
 Status: PROMOTION_WRITEBACK_DRY_RUN_BUILT
 Quality status: PASS
 writeback_mode: dry_run
 approved_promotion_candidate_count: 0
 writeback_plan_count: 0
 postgres_write_attempt_count: 0
 source_truth_mutation_allowed_count: 0
```

## Quality check

```bash
python scripts/check_trace_net_promotion_writeback_dry_run_v1_quality.py \
  --report-path local_data/organization/trace_net/promotion_writeback_dry_run/trace_net_promotion_writeback_dry_run_v1.json \
  --min-writeback-plans 0 \
  --require-promotion-gate-quality-pass \
  --write-json
```

## Build after an approved promotion candidate

If you record a promotion-type decision, rebuild decisions and the promotion gate first. Then run:

```bash
python scripts/build_trace_net_promotion_writeback_dry_run_v1.py \
  --promotion-gate local_data/organization/trace_net/human_review_promotion_gate/trace_net_human_review_promotion_gate_v1.json \
  --review-decisions local_data/organization/trace_net/human_review_decisions/trace_net_human_review_decisions_v1.json \
  --triage-report local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.json \
  --output-dir local_data/organization/trace_net/promotion_writeback_dry_run \
  --min-writeback-plans 1 \
  --require-promotion-gate-quality-pass \
  --quality
```

## Inspect plans

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("local_data/organization/trace_net/promotion_writeback_dry_run/trace_net_promotion_writeback_dry_run_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))

print("quality_status:", payload["quality_status"])
print("summary:", payload["summary"])

for plan in payload["writeback_plans"]:
    print()
    print("writeback_plan_id:", plan["writeback_plan_id"])
    print("planned_writeback_type:", plan["planned_writeback_type"])
    print("writeback_status:", plan["writeback_status"])
    print("target:", plan["target_type"], plan["target_id"])
    print("page_ids:", plan["page_ids"][:5])
    print("citation_ids:", plan["citation_ids"][:5])
    print("part_numbers:", plan["part_numbers"][:5])
    print("required_checks:", plan["required_checks"])
    print("missing_required_checks:", plan["missing_required_checks"])
    print("requires_writeback_gate:", plan["requires_writeback_gate"])
    print("requires_regression_after_writeback:", plan["requires_regression_after_writeback"])
    print("postgres_write_attempted:", plan["postgres_write_attempted"])
    print("can_answer_directly:", plan["can_answer_directly"])
    print("can_prove_claims:", plan["can_prove_claims"])
    print("can_mutate_source_truth:", plan["can_mutate_source_truth"])
PY
```

## Generated files

```text
trace_net_promotion_writeback_dry_run_v1.json
trace_net_promotion_writeback_dry_run_v1_plans.jsonl
trace_net_promotion_writeback_dry_run_v1_summary.json
trace_net_promotion_writeback_dry_run_v1_manifest.json
trace_net_promotion_writeback_dry_run_v1_quality.json
trace_net_promotion_writeback_dry_run_v1.md
trace_net_promotion_writeback_dry_run_v1.html
```

## Safety contract

Every plan has:

```text
writeback_mode = dry_run
postgres_write_attempted = false
qdrant_write_attempted = false
opensearch_write_attempted = false
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
source_truth_mutation_allowed = false
requires_writeback_gate = true
requires_regression_after_writeback = true
```

## Commit patch files

```bash
git add \
  tiff/trace_net_promotion_writeback_dry_run_v1.py \
  scripts/build_trace_net_promotion_writeback_dry_run_v1.py \
  scripts/check_trace_net_promotion_writeback_dry_run_v1_quality.py \
  tests/unit/test_trace_net_promotion_writeback_dry_run_v1.py \
  tests/unit/test_trace_net_promotion_writeback_dry_run_v1_quality.py \
  tests/unit/test_trace_net_promotion_writeback_dry_run_v1_script_imports.py \
  README_trace_net_promotion_writeback_dry_run_v1.md

git commit -m "Add TRACE-Net promotion writeback dry run v1"
```
