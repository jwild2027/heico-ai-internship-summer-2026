# TRACE-Net Feedback Context Validation v1.1

This patch upgrades the feedback graph overlay with context validation. Feedback is still recorded, but only feedback that matches the linked ask/answer context can generate advisory policy signals.

## What it validates

- Feedback query fingerprint matches the latest ask context.
- Affected pages appear in the grouped answer results.
- Expected pages appear in the grouped answer results, when provided.
- Ask/answer/grouped-result artifacts are present.

Events that fail validation are stored with `context_status=needs_review` and `policy_signal_eligible=false`. They do not generate boost/demote policy signals until reviewed.

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_feedback.py \
  tests/unit/test_tiff_trace_net_feedback_quality.py \
  -q
```

## Record feedback with explicit query context

```bash
python scripts/record_trace_net_feedback.py \
  --part-number 120-50645-009 \
  --rating thumbs_down \
  --reason-code wrong_page \
  --affected-page-id t_p_120_1176_p000320 \
  --expected-page-id t_p_120_1176_p000003 \
  --comment "p000003 was the useful evidence for this part."
```

If the latest ask run is for a different query, this event is retained but marked `needs_review`, so it cannot influence ranking yet.

## Rebuild graph

```bash
python scripts/build_trace_net_feedback_graph.py --open
```

## Quality checks

Strict validation for currently valid feedback only:

```bash
python scripts/check_trace_net_feedback_quality.py \
  --write-json \
  --min-events 1 \
  --min-policy-signals 1 \
  --min-policy-signal-eligible-events 1 \
  --max-context-warning-events 0 \
  --max-source-truth-mutations 0
```

Review-tolerant validation, allowing stored context warnings:

```bash
python scripts/check_trace_net_feedback_quality.py \
  --write-json \
  --min-events 1 \
  --max-source-truth-mutations 0
```

## Safety rule

Feedback can create advisory policy signals only after context validation. Feedback never mutates source truth, Evidence Consensus, or RAG eligibility.
