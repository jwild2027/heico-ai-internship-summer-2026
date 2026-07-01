# TRACE-Net Engineering Semantic Answer Quality Eval v1

H10 checks whether H9 intent-specific engineering answers actually answer the intent of the question, not only whether they have citations and safety counters.

## Purpose

This module evaluates existing `trace_net_engineering_intent_answer_composer_v1.json` manifests and writes:

- `trace_net_engineering_semantic_answer_quality_eval_v1.json`
- `trace_net_engineering_semantic_answer_quality_eval_v1_quality_check.json`
- `trace_net_engineering_semantic_answer_quality_eval_v1_records.csv`

It does not mutate source truth, answer permission, databases, OpenSearch, Qdrant, or Postgres.

## Semantic checks

The checker validates intent-specific answer shape for:

- unsupported interchangeability questions
- unsupported installation-safety questions
- limitation / cannot-prove questions
- troubleshooting nomenclature questions
- figure comparison questions
- evidence-support questions

Examples:

- Interchangeability answers must say TRACE-Net cannot prove interchangeability and must not treat same nomenclature as approval.
- Installation-safety answers must say figure evidence identifies a part but does not prove installation safety.
- Troubleshooting answers must mention visual-link field coverage and OCR recovery.
- Comparison answers must mention both figures and both part numbers.

## Build

```bash
python -B scripts/build_trace_net_engineering_semantic_answer_quality_eval_v1.py \
  --composer-root local_data/organization/trace_net \
  --output-dir local_data/organization/trace_net/engineering_semantic_answer_quality_eval_v1 \
  --min-semantic-records 5 \
  --min-semantic-passes 5 \
  --max-semantic-failures 0 \
  --max-missing-intent-requirements 0 \
  --max-unsupported-claims 0 \
  --max-summary-used-as-proof 0 \
  --max-invalid-citations 0 \
  --max-llava-only-part-identity-claims 0 \
  --max-unsafe 0 \
  --max-answer-permission 0 \
  --max-source-truth-mutation-allowed 0 \
  --max-write-attempts 0 \
  --require-quality-pass
```

## Check

```bash
python -B scripts/check_trace_net_engineering_semantic_answer_quality_eval_v1.py \
  --eval-set local_data/organization/trace_net/engineering_semantic_answer_quality_eval_v1/trace_net_engineering_semantic_answer_quality_eval_v1.json \
  --output local_data/organization/trace_net/engineering_semantic_answer_quality_eval_v1/trace_net_engineering_semantic_answer_quality_eval_v1_quality_check_cli.json \
  --require-quality-pass \
  --min-semantic-records 5 \
  --min-semantic-passes 5 \
  --max-semantic-failures 0 \
  --max-missing-intent-requirements 0 \
  --max-unsupported-claims 0 \
  --max-summary-used-as-proof 0 \
  --max-invalid-citations 0 \
  --max-llava-only-part-identity-claims 0 \
  --max-unsafe 0 \
  --max-answer-permission 0 \
  --max-source-truth-mutation-allowed 0 \
  --max-write-attempts 0
```
