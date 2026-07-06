# TRACE-Net Answer Context Pack v1 Answer-Support Expansion Fix

This patch fixes the Step 10 case where hybrid retrieval returns safe ranked pages but the immediate Qdrant hits are all route-only records, such as page profiles, context helpers, or source-existence records.

The context pack now performs a guarded same-page expansion:

```text
ranked hybrid page
-> same-page embedding candidates
-> select safe source_text_evidence / verified_part_evidence
-> require source trace + citation/source + authority gate flags
-> add as answer_support_candidate records
```

This does not allow answering yet. It only prepares a safer context pack for a future citation/authority answer composer.

## Safety contract

Expanded records must still satisfy:

```text
rag_bucket in {source_text_evidence, verified_part_evidence}
page_id present
source trace present
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
embedding_answer_authority_allowed = false
```

Route-only records remain route-only:

```text
page_retrieval_profile
context_retrieval_helper
source_evidence
derived_context
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_answer_context_pack_v1.py \
  tests/unit/test_trace_net_answer_context_pack_v1_quality.py \
  tests/unit/test_trace_net_answer_context_pack_v1_script_imports.py \
  -q
```

## Rebuild Step 10

```bash
python scripts/build_trace_net_answer_context_pack_v1.py \
  --ask-report local_data/organization/trace_net/ask_hybrid_flag/trace_net_ask_hybrid_flag_v1.json \
  --hybrid-report local_data/organization/trace_net/ask_hybrid_flag/hybrid_runtime/trace_net_hybrid_retrieval_sim_v1.json \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --page-profiles local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --output-dir local_data/organization/trace_net/answer_context_pack \
  --max-groups 8 \
  --max-page-answer-support-records 3 \
  --min-context-groups 1 \
  --min-context-records 1 \
  --min-answer-support-records 1 \
  --min-retrieval-only-records 1 \
  --require-ask-quality-pass \
  --require-hybrid-quality-pass \
  --require-regression-quality-pass \
  --require-embedding-dim 1024 \
  --quality
```

Expected summary fields include:

```text
answer_support_record_count: >=1
answer_support_expansion_record_count: >=1
retrieval_only_answer_allowed_count: 0
source_evidence_answer_allowed_count: 0
source_truth_mutation_allowed_count: 0
Quality status: PASS
```
