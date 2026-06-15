# TRACE-Net Vector Search Smoke v1

Step 6 verifies that TRACE-Net semantic vector search works over the two Qdrant collections loaded in Steps 5 and 5.5:

- `trace_net_embedding_candidates_v1` with 1,476 safe candidate/helper vectors.
- `trace_net_page_retrieval_profiles_v1` with 509 page-level route/profile vectors.

This smoke layer is intentionally retrieval-only. It does not compose answers, does not use Qdrant as source truth, and does not bypass Postgres/source/citation/trust gates. Every hit is checked for TRACE-Net safety payload fields.

## Outputs

The smoke runner writes local generated artifacts under:

```text
local_data/organization/trace_net/vector_search_smoke/
```

Generated files:

```text
trace_net_vector_search_smoke_v1.json
trace_net_vector_search_smoke_v1_hits.jsonl
trace_net_vector_search_smoke_v1_summary.json
trace_net_vector_search_smoke_v1_manifest.json
trace_net_vector_search_smoke_v1_quality.json
```

Do not commit generated `local_data/...` outputs unless you intentionally want local artifacts in Git.

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_vector_search_smoke_v1.py \
  tests/unit/test_trace_net_vector_search_smoke_v1_quality.py \
  -q
```

## Run smoke with Ollama BGE-M3

Make sure Qdrant and Ollama are running, then:

```bash
export QDRANT_URL="http://localhost:6333"
export OLLAMA_URL="http://localhost:11434"

python scripts/run_trace_net_vector_search_smoke_v1.py \
  --qdrant-url "$QDRANT_URL" \
  --candidate-collection trace_net_embedding_candidates_v1 \
  --page-profile-collection trace_net_page_retrieval_profiles_v1 \
  --embedding-mode ollama \
  --embedding-model bge-m3:latest \
  --embedding-dim 1024 \
  --ollama-url "$OLLAMA_URL" \
  --limit 5 \
  --min-smoke-queries 5 \
  --min-total-hits 50 \
  --min-candidate-hits 25 \
  --min-page-profile-hits 25 \
  --min-queries-with-candidate-hits 5 \
  --min-queries-with-page-profile-hits 5 \
  --min-candidate-collection-count 1476 \
  --min-page-profile-collection-count 509 \
  --require-candidate-count 1476 \
  --require-page-profile-count 509 \
  --require-embedding-dim 1024 \
  --quality
```

Expected shape:

```text
TRACE-Net vector search smoke v1
 Status: SMOKE_RAN
 Quality status: PASS
 embedding_mode: ollama
 embedding_model_name: bge-m3:latest
 embedding_dim: 1024
 smoke_query_count: 5
 total_hit_count: 50
 candidate_hit_count: 25
 page_profile_hit_count: 25
 candidate_collection_count: 1476
 page_profile_collection_count: 509
 unsafe_hit_payload_count: 0
 direct_answer_allowed_hit_count: 0
 claim_proof_allowed_hit_count: 0
```

## Quality check separately

```bash
python scripts/check_trace_net_vector_search_smoke_v1_quality.py \
  --smoke-path local_data/organization/trace_net/vector_search_smoke/trace_net_vector_search_smoke_v1.json \
  --min-smoke-queries 5 \
  --min-total-hits 50 \
  --min-candidate-hits 25 \
  --min-page-profile-hits 25 \
  --min-queries-with-candidate-hits 5 \
  --min-queries-with-page-profile-hits 5 \
  --min-candidate-collection-count 1476 \
  --min-page-profile-collection-count 509 \
  --require-candidate-count 1476 \
  --require-page-profile-count 509 \
  --require-embedding-dim 1024 \
  --write-json
```

## Optional custom queries

Custom queries can be supplied with repeated `--query` arguments:

```bash
python scripts/run_trace_net_vector_search_smoke_v1.py \
  --qdrant-url "$QDRANT_URL" \
  --embedding-mode ollama \
  --embedding-model bge-m3:latest \
  --embedding-dim 1024 \
  --ollama-url "$OLLAMA_URL" \
  --query "revision::T.P. 120/1176 revision history" \
  --query "parts::part number nomenclature item quantity" \
  --limit 5 \
  --quality
```

## Safety gates

The quality checker requires:

```text
missing_page_id_count = 0
missing_candidate_id_count = 0
missing_profile_id_count = 0
unsafe_hit_payload_count = 0
direct_answer_allowed_hit_count = 0
claim_proof_allowed_hit_count = 0
qdrant_source_truth_hit_count = 0
answer_authority_allowed_hit_count = 0
answer_capable_page_profile_count = 0
context_helper_answer_allowed_count = 0
source_evidence_answer_allowed_count = 0
source_evidence_claim_proof_allowed_count = 0
```

A Qdrant hit can retrieve and route. It cannot answer. Later hybrid retrieval must resolve each hit back through Postgres, source citations, and trust authority before any answer is composed.
