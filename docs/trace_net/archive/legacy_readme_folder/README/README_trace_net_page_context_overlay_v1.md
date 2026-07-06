# TRACE-Net Postgres Page Context Overlay v1

This patch loads the local page context graph overlay into PostgreSQL without rerunning the full Postgres graph loader.

It imports:

- `page_context_records`
- `page_context_topics`
- `page_context_highlighted_parts`
- `graph_nodes` where `node_type='page_context'`
- `graph_edges` with `HAS_CONTEXT`, `SUMMARIZES`, `TAGGED_AS`, and `HIGHLIGHTS_PART`

It treats page context as derived retrieval helper context, not source truth:

- `can_answer_directly = false`
- `can_support_answer = true`
- `canonical_source_truth = false`
- `requires_citation = true`

## Apply

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026
unzip -o ~/Downloads/heico_trace_net_page_context_overlay_v1.zip -d .
```

## Tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_page_context_overlay.py \
  tests/unit/test_tiff_trace_net_page_context_overlay_quality.py \
  -q
```

## Load context overlay into Postgres

```bash
python scripts/load_trace_net_page_context_overlay.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --context-file local_data/organization/context/page_contexts.json \
  --open
```

## Quality gate

```bash
python scripts/check_trace_net_page_context_overlay_quality.py \
  --write-json \
  --min-context-records 509 \
  --min-pages-with-context 509 \
  --min-context-graph-nodes 509 \
  --min-has-context-edges 509 \
  --min-tagged-as-edges 1 \
  --min-highlights-part-edges 1 \
  --max-missing-page-resolutions 0 \
  --max-direct-answer-context-records 0 \
  --max-canonical-source-truth-context-records 0 \
  --max-source-truth-mutations 0
```

## SQL checks

```bash
docker exec trace-net-postgres psql -U tracenet -d tracenet_dev \
  -c "select count(*) from page_context_records;"
```

```bash
docker exec trace-net-postgres psql -U tracenet -d tracenet_dev \
  -c "select count(*) from graph_nodes where node_type='page_context';"
```

```bash
docker exec trace-net-postgres psql -U tracenet -d tracenet_dev \
  -c "select edge_type, count(*) from graph_edges where edge_type in ('HAS_CONTEXT','SUMMARIZES','TAGGED_AS','HIGHLIGHTS_PART') group by edge_type order by edge_type;"
```

## Rebuild graph explorer UI

After the overlay is loaded, rebuild the UI:

```bash
python scripts/build_trace_net_graph_explorer.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --open
```

Then quality-check it:

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

If local file opening is blocked, serve it over localhost:

```bash
cd local_data/organization/trace_net/graph_explorer
python -m http.server 8765
```

Open:

```text
http://localhost:8765/trace_net_graph_explorer.html
```
