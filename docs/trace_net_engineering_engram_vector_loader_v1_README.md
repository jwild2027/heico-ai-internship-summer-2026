# TRACE-Net Engineering Engram Vector Loader v1

H18 converts the H17 Engineering Engram Memory Layer manifest into a local,
Qdrant-ready vector payload.

This is an artifact-only module. It does **not** connect to Qdrant, Postgres,
OpenSearch, Ollama, or any live service. It creates deterministic local vector
records so the payload shape can be tested, reviewed, committed, and later used
by a gated live loader.

## Input

- `trace_net_engineering_engram_memory_layers_v1.json`

## Output

- `trace_net_engineering_engram_vector_loader_v1.json`
- `trace_net_engineering_engram_vector_loader_v1.jsonl`
- `trace_net_engineering_engram_vector_loader_v1_quality_check.json`

## Memory role

Engram vector records are behavior-retrieval records. They are guidance only.
They must not be treated as proof for manual facts. Current `proof_context`
remains the only source for factual engineering claims.

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no source claims from Engram memory alone

## Why deterministic vectors?

H18 uses a deterministic hashing encoder so CI and Git workflows can validate
Qdrant-ready payload shape without requiring network calls, cloud embeddings,
GPU, or live Qdrant. A later module can swap the encoder behind a quality gate.
