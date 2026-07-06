# TRACE-Net Answer Context Pack v1

Step 10 converts a passed ask/hybrid retrieval run into a source-resolved answer context pack.

This is not a final answer composer. It does not call an LLM for answer generation, does not mutate source truth, and does not allow retrieval-only records to prove claims.

## Inputs

Default inputs:

```text
local_data/organization/trace_net/ask_hybrid_flag/trace_net_ask_hybrid_flag_v1.json
local_data/organization/trace_net/ask_hybrid_flag/hybrid_runtime/trace_net_hybrid_retrieval_sim_v1.json
local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json
local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json
```

The script resolves hybrid hits against the local embedding candidate and page profile artifacts.

## Outputs

```text
local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.json
local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1_groups.jsonl
local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1_records.jsonl
local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1_summary.json
local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1_manifest.json
local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1_quality.json
local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.md
local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.html
```

## Safety contract

The pack separates records into:

```text
retrieval_only_records
answer_support_records
blocked_records
```

Retrieval-only records include:

```text
page_retrieval_profile
context_retrieval_helper
source_evidence
derived_context
```

Answer-support candidate records include only:

```text
source_text_evidence
verified_part_evidence
```

Even answer-support records remain guarded:

```text
answer_composition_allowed = false
can_answer_directly = false
can_prove_claims = false
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
```

## Run

```bash
python scripts/build_trace_net_answer_context_pack_v1.py \
  --ask-report local_data/organization/trace_net/ask_hybrid_flag/trace_net_ask_hybrid_flag_v1.json \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --page-profiles local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --output-dir local_data/organization/trace_net/answer_context_pack \
  --max-groups 8 \
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

If the ask report does not include a usable hybrid runtime path, pass it explicitly:

```bash
--hybrid-report local_data/organization/trace_net/ask_hybrid_flag/hybrid_runtime/trace_net_hybrid_retrieval_sim_v1.json
```

## Quality check

```bash
python scripts/check_trace_net_answer_context_pack_v1_quality.py \
  --report-path local_data/organization/trace_net/answer_context_pack/trace_net_answer_context_pack_v1.json \
  --min-context-groups 1 \
  --min-context-records 1 \
  --min-answer-support-records 1 \
  --min-retrieval-only-records 1 \
  --require-ask-quality-pass \
  --require-hybrid-quality-pass \
  --require-regression-quality-pass \
  --require-embedding-dim 1024 \
  --write-json
```

Expected safety counts:

```text
unsafe_record_count = 0
missing_page_id_count = 0
missing_citation_required_count = 0
retrieval_only_answer_allowed_count = 0
page_profile_answer_allowed_count = 0
context_helper_answer_allowed_count = 0
source_evidence_answer_allowed_count = 0
direct_answer_allowed_record_count = 0
claim_proof_without_authority_count = 0
source_truth_mutation_allowed_count = 0
answer_composition_allowed_count = 0
llm_answer_allowed_count = 0
```

## TRACE-Net rule

```text
Hybrid retrieval finds candidates.
Answer context pack decides what may be shown to a future answer composer.
LLM answer generation remains off.
Every future claim still requires source/citation/trust authority.
```
