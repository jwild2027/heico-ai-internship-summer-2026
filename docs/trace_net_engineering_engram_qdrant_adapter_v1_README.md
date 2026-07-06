# TRACE-Net Engineering Engram Qdrant Adapter v1

H30 moves the Engineering Engram vector path from local Qdrant-ready artifacts toward live Qdrant integration while preserving TRACE-Net's safety boundary.

## Scope

- Input: H18 Engineering Engram vector loader manifest.
- Output: Qdrant point JSONL, local retrieval smoke records, adapter manifest, quality check.
- Default mode: artifact-only dry run, no live Qdrant IO.
- Optional live mode: Qdrant read/write only when explicit CLI flags are used.

## Safety contract

Engram vectors retrieve behavior guidance only. They do not prove manual/source claims. Source claims still require current `proof_context` citations.

Default counters remain zero:

- `qdrant_write_attempt_count`
- `qdrant_read_attempt_count`
- `postgres_write_attempt_count`
- `opensearch_write_attempt_count`
- `source_truth_mutation_allowed_count`
- `answer_permission_count`

Live Qdrant IO requires explicit flags:

- `--enable-live-qdrant-write`
- `--enable-live-qdrant-read`

## Follow-on

H31 should add the Postgres feedback/memory ledger. H32 should combine Self-RAG, CRAG, Qdrant/vector, feedback, and graph/vector routing into one gated runtime manifest.
