# TRACE-Net Engineering Engram Vector Retriever v1

H19 adds an artifact-only local retriever over the H18 Engram vector-loader records.
It is the dry-run retrieval step before any live Qdrant integration.

## Purpose

H17 created typed Engram memory layers. H18 converted those layer-tagged atoms into
Qdrant-ready vector payload records. H19 proves that those records can be retrieved
by question/task intent without contacting Qdrant or mutating any source-truth system.

## Memory role

The retrieved Engram records are behavior guidance only. They can shape answer style,
route awareness, critique, and repair behavior, but they cannot prove source claims.
Manual facts still require current `proof_context` citations.

## Safety contract

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes/uploads
- No source-truth mutation
- No answer permission
- No live Qdrant reads in this artifact-only version

## Build

```bash
python -B scripts/build_trace_net_engineering_engram_vector_retriever_v1.py \
  --vector-loader local_data/organization/trace_net/engineering_engram_vector_loader_v1/trace_net_engineering_engram_vector_loader_v1.json \
  --output-dir local_data/organization/trace_net/engineering_engram_vector_retriever_v1 \
  --top-k 5 \
  --min-queries 6 \
  --min-results-per-query 3 \
  --require-all-layers \
  --max-unsafe 0 \
  --max-write-attempts 0
```

## Check

```bash
python -B scripts/check_trace_net_engineering_engram_vector_retriever_v1.py \
  --vector-retriever local_data/organization/trace_net/engineering_engram_vector_retriever_v1/trace_net_engineering_engram_vector_retriever_v1.json \
  --min-queries 6 \
  --min-results-per-query 3 \
  --require-all-layers \
  --require-quality-pass \
  --require-no-answer-permission \
  --max-unsafe 0 \
  --max-write-attempts 0
```

## Next

H20 can use H19 retrieval records to inject only the most relevant Engram memories into
answer prompts instead of always selecting atoms locally. Live Qdrant should remain behind
explicit read/write gates.
