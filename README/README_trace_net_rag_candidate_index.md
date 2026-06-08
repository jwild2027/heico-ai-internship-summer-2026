# TRACE-Net RAG Candidate Indexer v1

This patch adds a local-artifact RAG candidate indexer. It reads the TRACE-Net RAG eligibility pools and creates safe, searchable candidate chunks for future BM25/vector/graph retrieval.

It does **not** embed vectors, call an LLM, or answer questions.

## Inputs

Default inputs:

```text
local_data/organization/trace_net/rag_eligibility/rag_eligible_source_evidence.jsonl
local_data/organization/trace_net/rag_eligibility/rag_eligible_verified_part_evidence.jsonl
local_data/organization/trace_net/rag_eligibility/rag_eligible_derived_context.jsonl
```

Optional enrichment inputs:

```text
local_data/organization/export/page_index.json
local_data/organization/table_extraction/table_tile_text_refined/table_tile_text_refined_records.jsonl
```

## Outputs

```text
local_data/organization/trace_net/rag_candidates/rag_candidate_chunks.jsonl
local_data/organization/trace_net/rag_candidates/rag_candidate_source_chunks.jsonl
local_data/organization/trace_net/rag_candidates/rag_candidate_verified_part_chunks.jsonl
local_data/organization/trace_net/rag_candidates/rag_candidate_derived_chunks.jsonl
local_data/organization/trace_net/rag_candidates/rag_candidate_summary.json
local_data/organization/trace_net/rag_candidates/rag_candidate_review.html
local_data/organization/trace_net/rag_candidates/rag_candidate_graph_nodes.json
local_data/organization/trace_net/rag_candidates/rag_candidate_graph_edges.json
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_rag_candidate_index.py \
  tests/unit/test_tiff_trace_net_rag_candidate_index_quality.py \
  -q
```

## Build candidates

```bash
python scripts/build_trace_net_rag_candidate_index.py --open
```

## Quality gate

```bash
python scripts/check_trace_net_rag_candidate_index_quality.py \
  --write-json \
  --min-records 931 \
  --min-pages 509 \
  --min-source-candidates 509 \
  --min-verified-part-candidates 360 \
  --min-derived-candidates 60 \
  --max-unsafe-candidate-records 0 \
  --max-empty-text-records 0 \
  --max-table-candidate-indexed-records 0 \
  --max-table-tiles-indexed-records 0
```

Expected shape using the current Stage 5b RAG eligibility pools:

```text
records: 931
source_candidate_records: 509
verified_part_candidate_records: 362
derived_context_candidate_records: 60
unsafe_candidate_records: 0
empty_text_records: 0
```

## Why this exists

The RAG eligibility builder decides what evidence is allowed into RAG. This indexer turns those allowed records into chunk-shaped artifacts future search/index code can consume.

The current buckets become:

```text
source_evidence -> safe source/citation chunks
verified_part_evidence -> safe part evidence chunks
derived_context -> safe derived table/visual context chunks
```

Excluded, routing-only, and preprocessing-only records are not indexed.
