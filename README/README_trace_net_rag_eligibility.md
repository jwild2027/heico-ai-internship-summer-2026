# TRACE-Net RAG Eligibility Builder v1

This patch adds a policy-controlled RAG eligibility artifact builder.

It reads the Stage 5b controlled decision view:

```text
local_data/organization/trace_net/confidence/stage5_control/trace_lc_stage5_policy_control_records.jsonl
```

and splits evidence into stable downstream pools:

```text
local_data/organization/trace_net/rag_eligibility/rag_eligible_source_evidence.jsonl
local_data/organization/trace_net/rag_eligibility/rag_eligible_verified_part_evidence.jsonl
local_data/organization/trace_net/rag_eligibility/rag_eligible_derived_context.jsonl
local_data/organization/trace_net/rag_eligibility/rag_excluded_records.jsonl
local_data/organization/trace_net/rag_eligibility/rag_eligibility_records.jsonl
local_data/organization/trace_net/rag_eligibility/rag_eligibility_summary.json
local_data/organization/trace_net/rag_eligibility/rag_eligibility_review.html
local_data/organization/trace_net/rag_eligibility/rag_eligibility_graph_nodes.json
local_data/organization/trace_net/rag_eligibility/rag_eligibility_graph_edges.json
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_rag_eligibility.py \
  tests/unit/test_tiff_trace_net_rag_eligibility_quality.py \
  -q
```

## Build RAG eligibility pools

```bash
python scripts/build_trace_net_rag_eligibility.py --open
```

## Quality gate

For the current Stage 5b run, expected counts are approximately:

```text
records: 1813
source evidence: 509
verified part evidence: 362
derived context: 60
unsafe: 0
```

Run:

```bash
python scripts/check_trace_net_rag_eligibility_quality.py \
  --write-json \
  --min-records 1813 \
  --min-pages 509 \
  --min-source-evidence-records 509 \
  --min-verified-part-records 360 \
  --min-derived-context-records 60 \
  --max-unsafe-rag-eligible-records 0 \
  --max-table-candidate-eligible-records 0 \
  --max-table-tiles-eligible-records 0
```

## Safety behavior

The builder prevents direct RAG eligibility for routing/preprocessing-only layers:

```text
table_candidate
table_tiles
```

It also blocks records with untraceable source status or D-tier RAG include attempts.

## Intended downstream use

Future indexing/RAG code should consume these eligibility pools instead of raw extraction records:

```text
source evidence pool -> source/citation index
verified part evidence pool -> part evidence index
derived context pool -> derived context index
excluded pool -> repair/review queue
```
