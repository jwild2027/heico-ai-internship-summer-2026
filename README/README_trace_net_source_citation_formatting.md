# TRACE-Net Source Citation Formatting v1

This patch adds a source/citation formatting layer for safe TRACE-Net RAG
candidate chunks. It builds a consistent citation object for every safe candidate
and annotates the latest search results when available.

It reads:

```text
local_data/organization/trace_net/rag_candidates/rag_candidate_chunks.jsonl
local_data/organization/trace_net/search/trace_net_search_results.jsonl
```

It writes:

```text
local_data/organization/trace_net/citations/trace_net_source_citations.jsonl
local_data/organization/trace_net/citations/trace_net_search_results_with_citations.jsonl
local_data/organization/trace_net/citations/trace_net_source_citation_summary.json
local_data/organization/trace_net/citations/trace_net_source_citation_review.html
local_data/organization/trace_net/citations/trace_net_source_citation_graph_nodes.json
local_data/organization/trace_net/citations/trace_net_source_citation_graph_edges.json
```

The citation object includes:

```text
citation_id
short_label
citation_text
citation_markdown
page_id
document_id
ATA
source URL
TIFF path
OCR path
RAG bucket
evidence layer
trust tier
usable confidence
```

Run:

```bash
python scripts/build_trace_net_source_citations.py --open
```

Quality:

```bash
python scripts/check_trace_net_source_citation_quality.py \
  --write-json \
  --min-citations 1426 \
  --min-pages 509 \
  --min-source-traceable 1426 \
  --max-unsafe-citations 0 \
  --max-missing-source-url 0
```

If you want to require citation annotation for the latest search results:

```bash
python scripts/check_trace_net_source_citation_quality.py \
  --write-json \
  --min-citations 1426 \
  --min-pages 509 \
  --min-source-traceable 1426 \
  --min-search-results-with-citations 1 \
  --max-unsafe-citations 0 \
  --max-missing-source-url 0
```
