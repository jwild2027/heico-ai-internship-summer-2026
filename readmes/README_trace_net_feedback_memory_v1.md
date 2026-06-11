# TRACE-Net Feedback Memory v1

Step 21 adds advisory feedback memory for TRACE-Net web UI feedback.

Users can submit:

- thumbs up / thumbs down
- comments
- issue tags
- target type: answer, claim, citation, page, retrieval group, table row/cell, visual region, community

Feedback is stored as raw feedback events and then converted into sanitized memory records.

## Safety rule

Feedback is memory, not evidence.

Feedback can:

- guide retrieval ranking
- mark pages/citations/claims as useful or needing review
- give the LLM safe advisory context
- help review/triage weak retrieval results

Feedback cannot:

- answer directly
- prove claims
- mutate source truth
- override citations
- override trust authority
- override the final answer gate

## Files

```text
tiff/trace_net_feedback_memory_v1.py
scripts/init_trace_net_feedback_memory_v1.py
scripts/record_trace_net_feedback_v1.py
scripts/build_trace_net_feedback_memory_v1.py
scripts/check_trace_net_feedback_memory_v1_quality.py
tests/unit/test_trace_net_feedback_memory_v1.py
tests/unit/test_trace_net_feedback_memory_v1_quality.py
tests/unit/test_trace_net_feedback_memory_v1_script_imports.py
```

## Local artifact outputs

```text
local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1_schema.sql
local_data/organization/trace_net/feedback_memory/trace_net_feedback_events_v1.jsonl
local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json
local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1_records.jsonl
local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1_events_snapshot.jsonl
local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1_summary.json
local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1_manifest.json
local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1_quality.json
local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.md
local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.html
```

## Postgres tables

The initializer writes SQL for two optional Postgres tables:

```text
trace_net_feedback_events
trace_net_feedback_memory_records
```

Use local JSON first. Use Postgres writeback only when ready:

```bash
python scripts/init_trace_net_feedback_memory_v1.py \
  --output-dir local_data/organization/trace_net/feedback_memory
```

Optional DB mode:

```bash
export TRACE_NET_DATABASE_URL="postgresql://tracenet:tracenet@localhost:5432/tracenet_dev"

python scripts/init_trace_net_feedback_memory_v1.py \
  --output-dir local_data/organization/trace_net/feedback_memory \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --write-postgres
```

## Record feedback

Example thumbs-up feedback on the final answer:

```bash
python scripts/record_trace_net_feedback_v1.py \
  --query "Which pages discuss manual revision history?" \
  --rating up \
  --target-type answer \
  --target-id trace_net_final_answer_gate_v1 \
  --answer-report local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json \
  --answer-mode final-gate \
  --retrieval-mode hybrid-simulate \
  --issue-tag helpful_answer \
  --comment "Helpful answer. Page 13 looks useful for revision history."
```

Example thumbs-down feedback on a citation:

```bash
python scripts/record_trace_net_feedback_v1.py \
  --query "Which pages discuss manual revision history?" \
  --rating down \
  --target-type citation \
  --target-id "cite:source_text:t_p_120_1176_p000048:c10c9ea562" \
  --page-id t_p_120_1176_p000048 \
  --citation-id "cite:source_text:t_p_120_1176_p000048:c10c9ea562" \
  --issue-tag irrelevant_page \
  --issue-tag wrong_page \
  --comment "This page seems less relevant for revision history."
```

## Build sanitized memory

```bash
python scripts/build_trace_net_feedback_memory_v1.py \
  --feedback-events local_data/organization/trace_net/feedback_memory/trace_net_feedback_events_v1.jsonl \
  --final-answer-report local_data/organization/trace_net/final_answer_gate/trace_net_final_answer_gate_v1.json \
  --leiden-communities local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json \
  --output-dir local_data/organization/trace_net/feedback_memory \
  --min-feedback-events 1 \
  --min-memory-records 1 \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_feedback_memory_v1_quality.py \
  --report-path local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json \
  --min-feedback-events 1 \
  --min-memory-records 1 \
  --write-json
```

Quality should pass with:

```text
raw_feedback_direct_to_llm_count = 0
feedback_can_answer_directly_count = 0
feedback_can_prove_claims_count = 0
feedback_can_mutate_source_truth_count = 0
```

## How the LLM may use feedback

Only sanitized memory records may be shown to the LLM.

Example safe advisory context:

```text
Feedback memory, advisory only:
- Prior feedback marked page t_p_120_1176_p000013 as helpful for similar revision-history queries.
- Prior feedback marked citation cite:...p000048... as less relevant for revision-history queries.

Rules:
- Feedback is not source evidence.
- Do not cite feedback as proof.
- Use feedback only to guide which cited source pages to inspect first.
```

The final answer still requires source evidence, citation, trust authority, and final answer gate approval.
