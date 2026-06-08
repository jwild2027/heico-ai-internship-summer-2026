# TRACE-Net Source Citation Formatter v1

This patch adds a reusable source citation formatting layer for safe TRACE-Net RAG candidates and latest search results.

It reads:

```text
local_data/organization/trace_net/rag_candidates/rag_candidate_chunks.jsonl
local_data/organization/trace_net/search/trace_net_search_results.jsonl
```

and writes:

```text
local_data/organization/trace_net/citations/trace_net_source_citations.jsonl
local_data/organization/trace_net/citations/trace_net_search_result_citations.jsonl
local_data/organization/trace_net/citations/trace_net_source_citation_summary.json
local_data/organization/trace_net/citations/trace_net_source_citation_review.md
local_data/organization/trace_net/citations/trace_net_source_citation_review.html
```

Run:

```bash
python scripts/build_trace_net_source_citations.py --open
```

Quality:

```bash
python scripts/check_trace_net_source_citation_quality.py \
  --write-json \
  --min-candidate-citations 1426 \
  --min-pages 509 \
  --min-complete-citations 1426 \
  --max-unsafe-citations 0 \
  --max-empty-formatted 0
```

If you want to include latest search-result citations too:

```bash
python scripts/check_trace_net_source_citation_quality.py \
  --write-json \
  --min-candidate-citations 1426 \
  --min-pages 509 \
  --min-complete-citations 1426 \
  --min-search-citations 1 \
  --max-unsafe-citations 0 \
  --max-empty-formatted 0
```

This layer does not decide eligibility. It only formats already-safe records into consistent citation objects.
