# TRACE-Net Search Result Grouper v1

This patch adds a page-level grouping layer for TRACE-Net local search results.
It reads the latest safe chunk-level search output and groups all supporting chunks by page while preserving source trace, buckets, trust tiers, confidence, matched parts/terms, and citation metadata when available.

## Inputs

```text
local_data/organization/trace_net/search/trace_net_search_results.jsonl
local_data/organization/trace_net/citations/trace_net_source_citations.jsonl
local_data/organization/trace_net/citations/trace_net_search_source_citations.jsonl
```

The citation files are optional. If they are present, grouped results keep citation IDs/markdown for supporting chunks.

## Outputs

```text
local_data/organization/trace_net/search/trace_net_search_grouped_results.json
local_data/organization/trace_net/search/trace_net_search_grouped_results.jsonl
local_data/organization/trace_net/search/trace_net_search_grouped_summary.json
local_data/organization/trace_net/search/trace_net_search_grouped_review.md
local_data/organization/trace_net/search/trace_net_search_grouped_review.html
local_data/organization/trace_net/search/trace_net_search_grouped_graph_nodes.json
local_data/organization/trace_net/search/trace_net_search_grouped_graph_edges.json
local_data/organization/trace_net/search/trace_net_search_grouped_quality.json
```

## Run

```bash
python scripts/group_trace_net_search_results.py --open
```

## Quality

```bash
python scripts/check_trace_net_search_group_quality.py \
  --write-json \
  --min-groups 1 \
  --min-pages 1 \
  --min-supporting-results 1 \
  --max-unsafe-groups 0 \
  --max-excluded-groups 0
```

For searches where you expect duplicate evidence buckets on the same page, you can require at least one multi-bucket group:

```bash
python scripts/check_trace_net_search_group_quality.py \
  --write-json \
  --min-groups 1 \
  --min-pages 1 \
  --min-supporting-results 1 \
  --min-groups-with-multiple-buckets 1 \
  --max-unsafe-groups 0 \
  --max-excluded-groups 0
```

## What this contributes

Chunk-level search is good for internal ranking, but user-facing retrieval should show page-level results.
This grouper creates results like:

```text
Page p000003
  score
  supporting evidence buckets
  matched part numbers
  source URL / TIFF / OCR
  supporting chunk list
```

It does not introduce unsafe results; it only groups the already-safe local search results.
