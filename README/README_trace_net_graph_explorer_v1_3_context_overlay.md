# TRACE-Net Graph Explorer v1.3 Context Overlay Fix

Adds Postgres page context overlay records to the interactive graph explorer.

New visible graph elements:

- `page_context` nodes
- `Page -> HAS_CONTEXT -> PageContext` edges
- `PageContext -> SUMMARIZES -> Page` edges
- `PageContext -> TAGGED_AS -> Topic` edges
- `PageContext -> HIGHLIGHTS_PART -> Part` edges
- page role nodes

This is read-only UI/export logic. It does not mutate PostgreSQL, trust tiers,
RAG eligibility, ranking, source truth, or feedback.

Run:

```bash
python scripts/build_trace_net_graph_explorer.py --database-url "$TRACE_NET_DATABASE_URL" --open
python scripts/check_trace_net_graph_explorer_quality.py --write-json --min-pages 509 --min-part-nodes 1 --min-candidate-nodes 1426 --min-citation-nodes 1 --min-has-candidate-edges 1426 --min-part-page-edges 1 --min-trust-edges 509 --min-context-nodes 509 --min-has-context-edges 509 --require-html-text
```
