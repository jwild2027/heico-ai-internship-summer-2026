# TRACE-Net Page Retrieval Profiles v1

Step 5.5 builds one safe page-level retrieval profile for each TRACE-Net manual page, then optionally embeds/loads those profiles into a separate Qdrant collection.

A page retrieval profile is a coarse routing/tunnel vector. It is not source truth, not answer authority, and not claim proof. A Qdrant hit on a page profile must resolve back through Postgres/source/citation/trust gates before answer use.

## Inputs

```text
Postgres pages table
Postgres graph_nodes / graph_edges tables when present
Postgres page_context_v2_records when present
local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json
local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json
local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/trace_net_graph_baseline_checkpoint_v1.json
```

## Build outputs

```text
local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json
local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.jsonl
local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1_rejected.jsonl
local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1_summary.json
local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1_manifest.json
local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1_quality.json
```

## JSON shape

Each generated page profile has this safety contract:

```json
{
  "record_type": "page_retrieval_profile",
  "rag_bucket": "page_retrieval_profile",
  "authority": "page_route_only",
  "answer_use_policy": "route_to_page_then_resolve_source_evidence",
  "page_id": "t_p_120_1176_p000001",
  "page_number": 1,
  "document_id": "t_p_120_1176",
  "ata_code": "25-21-00",
  "can_embed": true,
  "can_retrieve": true,
  "can_answer_directly": false,
  "can_prove_claims": false,
  "can_prove_source_truth": false,
  "canonical_source_truth": false,
  "can_mutate_source_truth": false,
  "requires_source_resolution": true,
  "requires_citation": true,
  "requires_authority_gate": true,
  "embedding_answer_authority_allowed": false,
  "known_parts": [],
  "known_nomenclature": [],
  "retrieval_cues": [],
  "query_tunnel_terms": [],
  "safe_candidate_bucket_counts": {
    "source_evidence": 1,
    "source_text_evidence": 1
  },
  "embedding_text": "Document: t_p_120_1176 ... Safety: route only ..."
}
```

## Build page profiles

```bash
export TRACE_NET_DATABASE_URL="postgresql://tracenet:tracenet@localhost:5432/tracenet_dev"

python scripts/build_trace_net_page_retrieval_profiles_v1.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --context-helpers local_data/organization/trace_net/context_retrieval_helpers/trace_net_context_retrieval_helpers_v1.json \
  --baseline-checkpoint local_data/organization/trace_net/baselines/graph_context_v2_nomenclature_v1/trace_net_graph_baseline_checkpoint_v1.json \
  --output-dir local_data/organization/trace_net/page_retrieval_profiles \
  --require-first-pages 1-50 \
  --min-profile-records 509 \
  --min-pages-with-profiles 509 \
  --min-source-trace-pages 509 \
  --min-context-v2-pages 50 \
  --min-profiles-with-retrieval-cues 50 \
  --require-baseline-quality-pass \
  --require-embedding-candidate-quality-pass \
  --require-context-helper-quality-pass \
  --quality
```

## Check profile quality

```bash
python scripts/check_trace_net_page_retrieval_profiles_v1_quality.py \
  --profiles-path local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --require-first-pages 1-50 \
  --min-profile-records 509 \
  --min-pages-with-profiles 509 \
  --min-source-trace-pages 509 \
  --min-context-v2-pages 50 \
  --min-profiles-with-retrieval-cues 50 \
  --require-baseline-quality-pass \
  --require-embedding-candidate-quality-pass \
  --require-context-helper-quality-pass \
  --write-json
```

## Embed/load all 509 page profiles into Qdrant

This uses deterministic local hash embeddings for plumbing/smoke tests. Later, replace this with real local model embeddings while keeping the same payload contract.

```bash
export QDRANT_URL="http://localhost:6333"

python scripts/load_trace_net_page_retrieval_profiles_qdrant_v1.py \
  --profiles-path local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --output-dir local_data/organization/trace_net/qdrant_page_retrieval_profiles \
  --qdrant-url "$QDRANT_URL" \
  --collection trace_net_page_retrieval_profiles_v1 \
  --embedding-mode hash \
  --embedding-dim 384 \
  --batch-size 128 \
  --recreate \
  --min-loaded-points 509 \
  --min-pages-with-points 509 \
  --min-source-trace-points 509 \
  --min-context-v2-points 50 \
  --require-profile-quality-pass \
  --require-exact-qdrant-count \
  --quality
```

## Check Qdrant quality

```bash
python scripts/check_trace_net_page_retrieval_profiles_qdrant_v1_quality.py \
  --manifest-path local_data/organization/trace_net/qdrant_page_retrieval_profiles/trace_net_page_retrieval_profiles_qdrant_v1_manifest.json \
  --qdrant-url "$QDRANT_URL" \
  --collection trace_net_page_retrieval_profiles_v1 \
  --min-loaded-points 509 \
  --min-pages-with-points 509 \
  --min-source-trace-points 509 \
  --min-context-v2-points 50 \
  --require-profile-quality-pass \
  --require-exact-qdrant-count \
  --write-json
```

## Progress output for the 509 page-profile embeddings

The Qdrant page-profile loader supports `--progress` for the 509 page-level routing embeddings. It prints progress while profiles are vectorized and while Qdrant batches are uploaded. This is still a route-only embedding layer: page profile hits cannot answer directly and must resolve through Postgres/source/citation/trust before answer use.

```bash
python scripts/load_trace_net_page_retrieval_profiles_qdrant_v1.py \
  --profiles-path local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --output-dir local_data/organization/trace_net/qdrant_page_retrieval_profiles \
  --qdrant-url "$QDRANT_URL" \
  --collection trace_net_page_retrieval_profiles_v1 \
  --embedding-mode hash \
  --embedding-dim 384 \
  --batch-size 128 \
  --progress \
  --progress-every 25 \
  --recreate \
  --min-loaded-points 509 \
  --min-pages-with-points 509 \
  --min-source-trace-points 509 \
  --min-context-v2-points 50 \
  --require-profile-quality-pass \
  --require-exact-qdrant-count \
  --quality
```

## Real embedding mode added

The page-profile Qdrant loader now supports local SentenceTransformers embeddings:

```bash
--embedding-mode bge-m3 --embedding-model BAAI/bge-m3 --embedding-dim 1024
```

Use `--progress` to show vectorization and upload progress for the 509 page profiles.
