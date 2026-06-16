# TRACE-Net Ask Hybrid Flag v1

Step 9 wires hybrid retrieval into the ask-facing workflow behind an explicit flag:

```text
--retrieval-mode hybrid-simulate
```

This is not final answer generation. It is an ask-side retrieval preview that runs the Step 7 hybrid retriever for a user query only after the Step 8 regression evaluation has passed.

## Safety contract

The module preserves the TRACE-Net boundary:

```text
Qdrant/Ollama vectors can retrieve.
Hybrid groups can rank and route.
Hybrid ask flag output cannot answer directly.
Hybrid ask flag output cannot prove claims.
Hybrid ask flag output cannot mutate source truth.
Every future answer must resolve through source evidence, citation, and trust authority.
```

## Files

```text
tiff/trace_net_ask_hybrid_flag_v1.py
scripts/run_trace_net_ask_hybrid_flag_v1.py
scripts/check_trace_net_ask_hybrid_flag_v1_quality.py
tests/unit/test_trace_net_ask_hybrid_flag_v1.py
tests/unit/test_trace_net_ask_hybrid_flag_v1_quality.py
tests/unit/test_trace_net_ask_hybrid_flag_v1_script_imports.py
README_trace_net_ask_hybrid_flag_v1.md
```

## Outputs

Generated local artifacts are written under:

```text
local_data/organization/trace_net/ask_hybrid_flag/
```

Expected files:

```text
trace_net_ask_hybrid_flag_v1.json
trace_net_ask_hybrid_flag_v1_groups.jsonl
trace_net_ask_hybrid_flag_v1_summary.json
trace_net_ask_hybrid_flag_v1_manifest.json
trace_net_ask_hybrid_flag_v1_quality.json
trace_net_ask_hybrid_flag_v1.md
trace_net_ask_hybrid_flag_v1.html
hybrid_runtime/
```

Do not commit generated `local_data/...` artifacts.

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_ask_hybrid_flag_v1.py \
  tests/unit/test_trace_net_ask_hybrid_flag_v1_quality.py \
  tests/unit/test_trace_net_ask_hybrid_flag_v1_script_imports.py \
  -q
```

## Run ask with the guarded hybrid flag

Make sure Ollama and Qdrant are running first:

```bash
docker start trace-net-qdrant
export QDRANT_URL="http://localhost:6333"
export OLLAMA_URL="http://localhost:11434"
```

Then run:

```bash
python scripts/run_trace_net_ask_hybrid_flag_v1.py \
  --query "Which pages discuss manual revision history?" \
  --retrieval-mode hybrid-simulate \
  --qdrant-url "$QDRANT_URL" \
  --candidate-collection trace_net_embedding_candidates_v1 \
  --page-profile-collection trace_net_page_retrieval_profiles_v1 \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --page-profiles local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --regression-report local_data/organization/trace_net/regression_eval/trace_net_regression_eval_v1.json \
  --vector-smoke-report local_data/organization/trace_net/vector_search_smoke/trace_net_vector_search_smoke_v1.json \
  --embedding-mode ollama \
  --embedding-model bge-m3:latest \
  --embedding-dim 1024 \
  --ollama-url "$OLLAMA_URL" \
  --top-k 8 \
  --max-groups 8 \
  --require-candidate-count 1476 \
  --require-page-profile-count 509 \
  --require-embedding-dim 1024 \
  --quality
```

Expected shape:

```text
TRACE-Net ask hybrid flag v1
 Status: ASK_RAN
 Quality status: PASS
 retrieval_mode: hybrid-simulate
 answer_status: NOT_COMPOSED_SIMULATION_ONLY
 regression_quality_status: PASS
 hybrid_quality_status: PASS
 ranked_group_count: >=1
 unsafe_group_count: 0
 direct_answer_allowed_group_count: 0
 claim_proof_allowed_group_count: 0
 source_truth_mutation_allowed_group_count: 0
```

## Run quality separately

```bash
python scripts/check_trace_net_ask_hybrid_flag_v1_quality.py \
  --report-path local_data/organization/trace_net/ask_hybrid_flag/trace_net_ask_hybrid_flag_v1.json \
  --min-ranked-groups 1 \
  --min-safe-groups 1 \
  --require-retrieval-mode hybrid-simulate \
  --require-embedding-dim 1024 \
  --write-json
```

Expected:

```text
TRACE-Net ask hybrid flag v1 quality
 Status: PASS
```

## Notes

The default mode is `off`. Hybrid retrieval only runs when the user explicitly passes:

```text
--retrieval-mode hybrid-simulate
```

This is the final guarded step before a future answer-composer integration. It is deliberately simulation-only.
