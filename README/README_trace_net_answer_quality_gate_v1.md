# TRACE-Net Answer Quality Gate v1

`trace_net_answer_quality_gate_v1` audits a Gemma/LLM answer against a TRACE-Net context pack, especially the anchor-aware graph/Leiden context pack for exact part-number questions.

## Purpose

The gate verifies that a final answer:

- cites valid evidence labels, such as `[E1]`;
- mentions the queried part number;
- cites at least one direct exact proof anchor when direct proof exists;
- does not turn related variants into interchangeable replacements without proof;
- does not treat graph/Leiden/community relation as source-truth proof;
- keeps the TRACE-Net safety contract: dry-run only, no DB writes, no answer permission, no source-truth mutation.

## Typical build

```bash
python scripts/build_trace_net_answer_quality_gate_v1.py \
  --context-pack local_data/organization/trace_net/anchor_aware_graph_leiden_expander_gemma4_native_001/trace_net_anchor_aware_graph_leiden_expander_v1.json \
  --answer-file local_data/organization/trace_net/raw_to_answer_context_engineered_native_gemma4_001/trace_net_raw_to_answer_context_engineered_native_v1_answer.md \
  --output-dir local_data/organization/trace_net/answer_quality_gate_gemma4_native_001 \
  --require-source-quality-pass \
  --quality
```

## Typical check

```bash
python scripts/check_trace_net_answer_quality_gate_v1_quality.py \
  --report-path local_data/organization/trace_net/answer_quality_gate_gemma4_native_001/trace_net_answer_quality_gate_v1.json \
  --write-json \
  --min-records 1 \
  --min-citations 1 \
  --min-valid-citations 1 \
  --max-invalid-citations 0 \
  --max-unsupported-claim-sentences 0 \
  --max-violation-records 0 \
  --require-source-quality-pass \
  --require-answer-quality-pass \
  --require-direct-proof-citation \
  --require-query-part-mentioned \
  --require-no-unsupported-interchangeability \
  --require-no-graph-proof-overstatement \
  --require-no-human-review-required \
  --max-unsafe 0 \
  --require-no-answer-permission \
  --require-no-source-truth-mutation \
  --require-no-write-attempts
```

## Outputs

- `trace_net_answer_quality_gate_v1.json`
- `trace_net_answer_quality_gate_v1_records.csv`
- `trace_net_answer_quality_gate_v1_violations.csv`
- `trace_net_answer_quality_gate_v1_quality_check.json`
- `trace_net_answer_quality_gate_v1.md`
