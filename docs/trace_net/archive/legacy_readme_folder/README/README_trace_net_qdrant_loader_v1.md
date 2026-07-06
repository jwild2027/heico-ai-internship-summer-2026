# TRACE-Net Qdrant Loader v1

Step 5 loads the safe Step 4 embedding candidates into a local Qdrant collection.

Qdrant is treated as a rebuildable vector index only. It is not source truth, not answer authority, and not a citation replacement. Every point payload carries trace IDs and safety flags so a later vector hit can be resolved back through Postgres/source/citation/trust gates before answer use.

## Files

```text
tiff/trace_net_qdrant_loader_v1.py
scripts/load_trace_net_qdrant_embeddings_v1.py
scripts/check_trace_net_qdrant_loader_v1_quality.py
tests/unit/test_trace_net_qdrant_loader_v1.py
tests/unit/test_trace_net_qdrant_loader_v1_quality.py
README_trace_net_qdrant_loader_v1.md
```

## Input

Default input from Step 4:

```text
local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json
```

Expected current checkpoint shape:

```text
1476 safe embedding candidates
1426 RAG/source candidates
50 context retrieval helper candidates
0 unsafe embedding candidates
```

## Outputs

Default output directory:

```text
local_data/organization/trace_net/qdrant_loader/
```

Generated local artifacts:

```text
trace_net_qdrant_loader_v1_manifest.json
trace_net_qdrant_loader_v1_summary.json
trace_net_qdrant_loader_v1_quality.json
trace_net_qdrant_loader_v1_rejected.jsonl
trace_net_qdrant_loader_v1_points_preview.jsonl
```

The preview file intentionally stores payloads and vector dimensions, not full vectors, to keep local artifacts small. Full vectors are generated in memory and upserted into Qdrant.

## Embedding behavior

Default mode:

```text
--embedding-mode hash
```

This uses a deterministic local hash embedding for plumbing, loading, and smoke testing. It is reproducible and dependency-free, but it is not a production semantic embedding model. Later, a local embedding model can replace it by adding precomputed vectors and using:

```text
--embedding-mode existing
```

## Safety contract

Every Qdrant payload is forced to include safe index behavior:

```text
qdrant_is_source_truth = false
qdrant_can_answer_directly = false
qdrant_can_prove_claims = false
must_resolve_through_postgres = true
must_pass_authority_gate = true
must_use_source_citation = true
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
embedding_answer_authority_allowed = false
can_mutate_source_truth = false
can_override_trust = false
can_replace_citation = false
```

Retrieval-only buckets remain retrieval-only:

```text
source_evidence
derived_context
context_retrieval_helper
```

They can help route/rank/search. They cannot answer or prove claims from the vector payload.

## Git Bash usage

From repo root:

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026
```

Run tests:

```bash
python -m pytest \
  tests/unit/test_trace_net_qdrant_loader_v1.py \
  tests/unit/test_trace_net_qdrant_loader_v1_quality.py \
  -q
```

Check Qdrant:

```bash
export QDRANT_URL="http://localhost:6333"
curl -s "$QDRANT_URL/collections" | head -c 500
```

Load Qdrant:

```bash
python scripts/load_trace_net_qdrant_embeddings_v1.py \
  --candidates-path local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --output-dir local_data/organization/trace_net/qdrant_loader \
  --qdrant-url "$QDRANT_URL" \
  --collection trace_net_embedding_candidates_v1 \
  --embedding-mode hash \
  --embedding-dim 384 \
  --batch-size 128 \
  --recreate \
  --require-first-pages 1-50 \
  --min-loaded-points 1476 \
  --min-rag-points 1426 \
  --min-context-helper-points 50 \
  --min-pages-with-points 509 \
  --require-candidate-quality-pass \
  --require-exact-qdrant-count \
  --quality
```

Run quality separately:

```bash
python scripts/check_trace_net_qdrant_loader_v1_quality.py \
  --manifest-path local_data/organization/trace_net/qdrant_loader/trace_net_qdrant_loader_v1_manifest.json \
  --qdrant-url "$QDRANT_URL" \
  --collection trace_net_embedding_candidates_v1 \
  --require-first-pages 1-50 \
  --min-loaded-points 1476 \
  --min-rag-points 1426 \
  --min-context-helper-points 50 \
  --min-pages-with-points 509 \
  --require-candidate-quality-pass \
  --require-exact-qdrant-count \
  --write-json
```

Expected output:

```text
TRACE-Net Qdrant loader v1
 Status: LOADED
 loaded_point_count: 1476
 qdrant_count: 1476
 rag_candidate_point_count: 1426
 context_helper_point_count: 50
 page_count: 509
 unsafe_qdrant_payload_count: 0
 rejected_count: 0
 Quality status: PASS
```

## Optional dry run

Use this to build artifacts and quality output without touching Qdrant:

```bash
python scripts/load_trace_net_qdrant_embeddings_v1.py \
  --candidates-path local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --output-dir local_data/organization/trace_net/qdrant_loader \
  --embedding-mode hash \
  --embedding-dim 384 \
  --dry-run \
  --require-first-pages 1-50 \
  --min-loaded-points 1476 \
  --min-rag-points 1426 \
  --min-context-helper-points 50 \
  --min-pages-with-points 509 \
  --require-candidate-quality-pass \
  --quality
```


## Real embedding mode added

This loader now supports local SentenceTransformers embeddings:

```bash
--embedding-mode bge-m3 --embedding-model BAAI/bge-m3 --embedding-dim 1024
```

Hash mode remains available for smoke tests only.
