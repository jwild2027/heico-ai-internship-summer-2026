# TRACE-Net Hybrid Retrieval Simulation v1

Step 7 merges the two Qdrant retrieval layers into safe ranked retrieval groups:

- `trace_net_page_retrieval_profiles_v1` for page-level routing over all 509 pages.
- `trace_net_embedding_candidates_v1` for safe candidate/helper retrieval over 1,476 records.

This is still a simulation. It does not answer questions, mutate source truth, change trust tiers, modify RAG eligibility, or wire into ask. The output is a ranked set of retrieval groups that must later resolve through Postgres/source/citation/trust before any answer use.

This version resolves Qdrant hits back to local TRACE-Net JSON artifacts:

```text
local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json
local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json
local_data/organization/trace_net/vector_search_smoke/trace_net_vector_search_smoke_v1.json
```

## Files

```text
tiff/trace_net_hybrid_retrieval_sim_v1.py
scripts/run_trace_net_hybrid_retrieval_sim_v1.py
scripts/check_trace_net_hybrid_retrieval_sim_v1_quality.py
tests/unit/test_trace_net_hybrid_retrieval_sim_v1.py
tests/unit/test_trace_net_hybrid_retrieval_sim_v1_quality.py
tests/unit/test_trace_net_hybrid_retrieval_sim_v1_script_imports.py
README_trace_net_hybrid_retrieval_sim_v1.md
```

## Outputs

Generated local artifacts are written under:

```text
local_data/organization/trace_net/hybrid_retrieval_sim/
```

Expected generated files:

```text
trace_net_hybrid_retrieval_sim_v1.json
trace_net_hybrid_retrieval_sim_v1_results.jsonl
trace_net_hybrid_retrieval_sim_v1_groups.jsonl
trace_net_hybrid_retrieval_sim_v1_summary.json
trace_net_hybrid_retrieval_sim_v1_manifest.json
trace_net_hybrid_retrieval_sim_v1_quality.json
```

Do not commit generated `local_data/...` outputs.

## Run tests

```bash
python -m pytest \
  tests/unit/test_trace_net_hybrid_retrieval_sim_v1.py \
  tests/unit/test_trace_net_hybrid_retrieval_sim_v1_quality.py \
  tests/unit/test_trace_net_hybrid_retrieval_sim_v1_script_imports.py \
  -q
```

## Run the hybrid simulation

Make sure Qdrant and Ollama are running:

```bash
docker start trace-net-qdrant

export QDRANT_URL="http://localhost:6333"
export OLLAMA_URL="http://localhost:11434"
```

Run:

```bash
python scripts/run_trace_net_hybrid_retrieval_sim_v1.py \
  --qdrant-url "$QDRANT_URL" \
  --candidate-collection trace_net_embedding_candidates_v1 \
  --page-profile-collection trace_net_page_retrieval_profiles_v1 \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --page-profiles local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --vector-smoke-report local_data/organization/trace_net/vector_search_smoke/trace_net_vector_search_smoke_v1.json \
  --embedding-mode ollama \
  --embedding-model bge-m3:latest \
  --embedding-dim 1024 \
  --ollama-url "$OLLAMA_URL" \
  --top-k 8 \
  --max-groups 8 \
  --min-hybrid-queries 5 \
  --min-queries-with-results 5 \
  --min-grouped-results 25 \
  --min-candidate-hits 25 \
  --min-page-profile-hits 25 \
  --min-resolved-candidate-hits 25 \
  --min-resolved-page-profile-hits 25 \
  --min-candidate-collection-count 1476 \
  --min-page-profile-collection-count 509 \
  --require-candidate-count 1476 \
  --require-page-profile-count 509 \
  --require-embedding-dim 1024 \
  --require-vector-smoke-quality-pass \
  --progress \
  --quality
```

Expected shape:

```text
TRACE-Net hybrid retrieval simulation v1
 Status: SIM_RAN
 Quality status: PASS
 embedding_mode: ollama
 embedding_model_name: bge-m3:latest
 embedding_dim: 1024
 hybrid_query_count: 5
 grouped_result_count: >=25
 candidate_hit_count: >=25
 page_profile_hit_count: >=25
 resolved_candidate_hit_count: >=25
 resolved_page_profile_hit_count: >=25
 candidate_collection_count: 1476
 page_profile_collection_count: 509
 unsafe_result_count: 0
 unsafe_hit_payload_count: 0
 direct_answer_allowed_result_count: 0
 claim_proof_allowed_without_authority_count: 0
 source_truth_mutation_allowed_count: 0
```

## Run quality separately

```bash
python scripts/check_trace_net_hybrid_retrieval_sim_v1_quality.py \
  --report-path local_data/organization/trace_net/hybrid_retrieval_sim/trace_net_hybrid_retrieval_sim_v1.json \
  --qdrant-url "$QDRANT_URL" \
  --candidate-collection trace_net_embedding_candidates_v1 \
  --page-profile-collection trace_net_page_retrieval_profiles_v1 \
  --min-hybrid-queries 5 \
  --min-queries-with-results 5 \
  --min-grouped-results 25 \
  --min-candidate-hits 25 \
  --min-page-profile-hits 25 \
  --min-resolved-candidate-hits 25 \
  --min-resolved-page-profile-hits 25 \
  --min-candidate-collection-count 1476 \
  --min-page-profile-collection-count 509 \
  --require-candidate-count 1476 \
  --require-page-profile-count 509 \
  --require-embedding-dim 1024 \
  --require-vector-smoke-quality-pass \
  --write-json
```

## Inspect top groups

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("local_data/organization/trace_net/hybrid_retrieval_sim/trace_net_hybrid_retrieval_sim_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))

print("quality_status:", payload.get("quality", {}).get("status") or payload.get("quality_status"))
print("summary:", payload["summary"])

for query_result in payload["query_results"][:2]:
    print("\nQUERY:", query_result["query_id"], query_result["query"])
    for group in query_result["ranked_groups"][:3]:
        print(
            group["rank"],
            group["page_id"],
            group["hybrid_score"],
            group["safety_status"],
            "page_hits=", group["page_profile_hit_count"],
            "candidate_hits=", group["candidate_hit_count"],
            "answer_allowed=", group["answer_allowed"],
        )
PY
```

## TRACE-Net safety rule

Hybrid retrieval can rank and group. It cannot answer.

The output groups always carry:

```text
answer_allowed = false
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
```

The later answer path must still do:

```text
hybrid group -> Postgres/source resolution -> citation -> trust authority -> answer gate
```
