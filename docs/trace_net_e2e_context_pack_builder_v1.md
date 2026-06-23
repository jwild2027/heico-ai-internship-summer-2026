# TRACE-Net E2E Context Pack Builder v1

This module consumes `trace_net_e2e_hybrid_retrieval_runtime_v1.json` and creates local context packs for later final-gate review.

It is intentionally retrieval-only. It does not answer, prove claims, mutate source truth, or write to Postgres, Qdrant, OpenSearch, or upload anything.

## Inputs

- `local_data/organization/trace_net/e2e_hybrid_retrieval_runtime/trace_net_e2e_hybrid_retrieval_runtime_v1.json`

## Outputs

- `trace_net_e2e_context_pack_builder_v1.json`
- `trace_net_e2e_context_pack_builder_v1_quality.json`
- `trace_net_e2e_context_packs_v1.jsonl`
- `trace_net_e2e_context_items_v1.jsonl`
- `trace_net_e2e_context_pack_builder_v1_inspect.md`

## Safety contract

- `answer_permission=false`
- `can_answer_directly=false`
- `can_prove_claims=false`
- `source_truth_mutation_allowed=false`
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes/uploads

## Build

```bash
python scripts/build_trace_net_e2e_context_pack_builder_v1.py \
  --e2e-hybrid-retrieval-runtime local_data/organization/trace_net/e2e_hybrid_retrieval_runtime/trace_net_e2e_hybrid_retrieval_runtime_v1.json \
  --output-dir local_data/organization/trace_net/e2e_context_pack_builder \
  --top-k 5 \
  --min-source-retrieval-groups 5 \
  --min-context-packs 5 \
  --min-context-packs-with-items 5 \
  --min-total-context-items 20 \
  --min-pages-with-context-items 2 \
  --min-citation-ready-items 20 \
  --min-source-trace-ready-items 20 \
  --min-field-count 3 \
  --max-unsafe-records 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-source-runtime-quality-pass \
  --require-no-answer-permission \
  --quality
```

## Check

```bash
python scripts/check_trace_net_e2e_context_pack_builder_v1_quality.py \
  --report-path local_data/organization/trace_net/e2e_context_pack_builder/trace_net_e2e_context_pack_builder_v1.json \
  --min-source-retrieval-groups 5 \
  --min-context-packs 5 \
  --min-context-packs-with-items 5 \
  --min-total-context-items 20 \
  --min-pages-with-context-items 2 \
  --min-citation-ready-items 20 \
  --min-source-trace-ready-items 20 \
  --min-field-count 3 \
  --max-unsafe-records 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-source-runtime-quality-pass \
  --require-no-answer-permission \
  --write-json
```
