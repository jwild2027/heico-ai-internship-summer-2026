# TRACE-Net Local Search Harness v1

This patch adds a dependency-free local search layer over the safe TRACE-Net RAG candidate index.

It searches only:

```text
local_data/organization/trace_net/rag_candidates/rag_candidate_chunks.jsonl
```

It does not call an LLM, create embeddings, mutate the graph, or read excluded raw extraction artifacts.

## Files

```text
tiff/trace_net_rag_search.py
tiff/trace_net_rag_search_quality.py
scripts/search_trace_net_rag_candidates.py
scripts/check_trace_net_rag_search_quality.py
tests/unit/test_tiff_trace_net_rag_search.py
tests/unit/test_tiff_trace_net_rag_search_quality.py
```

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_rag_search.py \
  tests/unit/test_tiff_trace_net_rag_search_quality.py \
  -q
```

## Example searches

Exact part-number search:

```bash
python scripts/search_trace_net_rag_candidates.py \
  --part-number 120-50645-009 \
  --top-k 10 \
  --open
```

Keyword search:

```bash
python scripts/search_trace_net_rag_candidates.py \
  --query "seat bottom backrest" \
  --top-k 10 \
  --open
```

Exact page/source search:

```bash
python scripts/search_trace_net_rag_candidates.py \
  --page-id t_p_120_1176_p000010 \
  --top-k 10 \
  --open
```

Bucket-filtered search:

```bash
python scripts/search_trace_net_rag_candidates.py \
  --query "120-50645-009" \
  --bucket verified_part_evidence,derived_context \
  --top-k 10 \
  --open
```

## Quality gate

```bash
python scripts/check_trace_net_rag_search_quality.py \
  --write-json \
  --min-results 1 \
  --max-unsafe-results 0 \
  --max-excluded-results 0
```

For exact part-number searches, you can require at least one verified part result:

```bash
python scripts/check_trace_net_rag_search_quality.py \
  --write-json \
  --min-results 1 \
  --min-verified-part-results 1 \
  --max-unsafe-results 0 \
  --max-excluded-results 0
```

## Outputs

```text
local_data/organization/trace_net/search/trace_net_search_results.json
local_data/organization/trace_net/search/trace_net_search_results.jsonl
local_data/organization/trace_net/search/trace_net_search_summary.json
local_data/organization/trace_net/search/trace_net_search_review.md
local_data/organization/trace_net/search/trace_net_search_review.html
local_data/organization/trace_net/search/trace_net_search_quality.json
```

## Scoring

The v1 scorer combines:

```text
exact part-number matches
exact page-id matches
keyword/token matches
phrase matches
bucket boosts
trust tier boost
usable confidence boost
```

Trust/confidence/bucket scores are tie-breakers only. For a query, a record must have an actual lexical, page, phrase, or part-number match to be returned.

