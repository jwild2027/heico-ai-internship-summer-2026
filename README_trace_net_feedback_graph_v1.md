# TRACE-Net Feedback Graph v1

This patch adds an advisory feedback layer for TRACE-Net ask/answer runs.

It lets a UI or CLI record thumbs-up/thumbs-down/neutral feedback with reason codes and optional affected pages, expected pages, affected candidate IDs, and comments. The feedback is written as an overlay graph and does not mutate source truth, trust tiers, ranking, or RAG eligibility.

## Files

```text
tiff/trace_net_feedback.py
tiff/trace_net_feedback_quality.py
scripts/record_trace_net_feedback.py
scripts/build_trace_net_feedback_graph.py
scripts/check_trace_net_feedback_quality.py
tests/unit/test_tiff_trace_net_feedback.py
tests/unit/test_tiff_trace_net_feedback_quality.py
```

## Record feedback

Example downvote on a page result:

```bash
python scripts/record_trace_net_feedback.py \
  --rating thumbs_down \
  --reason-code wrong_page \
  --reason-code citation_not_supporting_answer \
  --affected-page-id t_p_120_1176_p000320 \
  --expected-page-id t_p_120_1176_p000003 \
  --comment "p000003 was the useful evidence for this part." \
  --open
```

Example upvote:

```bash
python scripts/record_trace_net_feedback.py \
  --rating thumbs_up \
  --reason-code answer_correct \
  --affected-page-id t_p_120_1176_p000003
```

## Rebuild feedback graph

```bash
python scripts/build_trace_net_feedback_graph.py --open
```

## Quality gate

```bash
python scripts/check_trace_net_feedback_quality.py \
  --write-json \
  --min-events 1 \
  --max-source-truth-mutations 0 \
  --min-policy-signals 1
```

## Outputs

```text
local_data/organization/trace_net/feedback/feedback_events.jsonl
local_data/organization/trace_net/feedback/feedback_summary.json
local_data/organization/trace_net/feedback/feedback_graph_nodes.json
local_data/organization/trace_net/feedback/feedback_graph_edges.json
local_data/organization/trace_net/feedback/feedback_policy_signals.jsonl
local_data/organization/trace_net/feedback/feedback_review.md
local_data/organization/trace_net/feedback/feedback_review.html
local_data/organization/trace_net/feedback/feedback_quality.json
```

## Safety policy

Feedback is advisory only.

```text
Feedback can create review/ranking signals.
Feedback cannot mutate source truth.
Feedback cannot directly include excluded records in RAG.
Feedback cannot bypass Evidence Consensus or TRACE-LC gates.
```

The generated policy signals are intended for later simulation before any ranking changes are applied.
