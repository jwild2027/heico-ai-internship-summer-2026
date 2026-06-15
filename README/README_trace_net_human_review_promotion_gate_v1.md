# TRACE-Net Human Review Promotion Gate v1

This module evaluates human review decisions that request stronger evidence promotion.

It is intentionally conservative:

- reviewer decisions are advisory inputs;
- the promotion gate is read-only;
- it never mutates source truth, graph truth, Qdrant, OpenSearch, or Postgres;
- it never grants direct answer authority;
- it never lets review comments prove claims.

## Inputs

Primary input:

```text
local_data/organization/trace_net/human_review_decisions/trace_net_human_review_decisions_v1.json
```

Optional support inputs:

```text
local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.json
local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json
local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json
local_data/organization/trace_net/graph_overlay_part_property_normalizer/trace_net_graph_overlay_part_property_normalizer_v1.json
```

## What the gate checks

For promotion-candidate decisions, it checks traceability and support:

- safe review decision;
- page/source trace when relevant;
- citation support when required;
- table-repair support for table repair promotion;
- catalog/graph/candidate support for part-link promotion;
- special review handling for callout promotion.

Decision types that can request promotion:

```text
approve
confirm_blank
confirm_table_repair
confirm_callout
confirm_part_link
```

Non-promotion decisions, such as `reject` and `needs_more_review`, are preserved as non-promotion records.

## Output

```text
local_data/organization/trace_net/human_review_promotion_gate/
```

Files:

```text
trace_net_human_review_promotion_gate_v1.json
trace_net_human_review_promotion_gate_v1_records.jsonl
trace_net_human_review_promotion_gate_v1_summary.json
trace_net_human_review_promotion_gate_v1_manifest.json
trace_net_human_review_promotion_gate_v1_quality.json
trace_net_human_review_promotion_gate_v1.md
trace_net_human_review_promotion_gate_v1.html
```

## Build

```bash
python scripts/build_trace_net_human_review_promotion_gate_v1.py \
  --review-decisions local_data/organization/trace_net/human_review_decisions/trace_net_human_review_decisions_v1.json \
  --triage-report local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --graph-overlay-part-normalizer local_data/organization/trace_net/graph_overlay_part_property_normalizer/trace_net_graph_overlay_part_property_normalizer_v1.json \
  --output-dir local_data/organization/trace_net/human_review_promotion_gate \
  --min-review-decisions 1 \
  --require-source-decision-quality-pass \
  --require-source-triage-quality-pass \
  --quality
```

For the current local decisions that include `reject` and `needs_more_review`, it is normal for promotion evaluation count to be zero.

After recording an approved decision like `confirm_table_repair`, rerun with:

```bash
--min-promotion-evaluations 1
```

## Quality check

```bash
python scripts/check_trace_net_human_review_promotion_gate_v1_quality.py \
  --report-path local_data/organization/trace_net/human_review_promotion_gate/trace_net_human_review_promotion_gate_v1.json \
  --min-review-decisions 1 \
  --require-source-decision-quality-pass \
  --write-json
```

## Safety contract

Promotion gate records are controlled eligibility records only:

```text
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
source_truth_mutation_allowed = false
final_answer_allowed = false
raw_feedback_direct_to_llm = false
```

Approved promotion records still require a later writeback/promotion execution gate and regression checks before any persistent trust or graph status changes.
