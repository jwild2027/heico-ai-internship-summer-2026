# TRACE-Net Graph Explorer v1

Builds a local interactive HTML graph explorer from the current PostgreSQL TRACE-Net graph/evidence data.

This is a graph navigation UI, not a tree. You can search/click parts, pages, candidates, citations, buckets, OCR classes, sources, and trust nodes. Clicking any node recenters the view and shows its neighbors, so small child-like nodes such as part numbers can connect directly to larger page nodes without forcing navigation back to a root.

## Build

```bash
python scripts/build_trace_net_graph_explorer.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --open
```

## Quality

```bash
python scripts/check_trace_net_graph_explorer_quality.py \
  --write-json \
  --min-pages 509 \
  --min-part-nodes 1 \
  --min-candidate-nodes 1426 \
  --min-citation-nodes 1 \
  --min-has-candidate-edges 1426 \
  --min-part-page-edges 1 \
  --min-trust-edges 509 \
  --require-html-text
```

## Outputs

```text
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer.html
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_data.json
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_summary.json
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_nodes.json
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_edges.json
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_quality.json
```

## Notes

- Does not mutate Postgres.
- Does not change trust, RAG eligibility, feedback, or ranking.
- Uses safe candidate chunks and trust overlays already loaded into Postgres.
- Embeds graph data directly into a standalone HTML file.
