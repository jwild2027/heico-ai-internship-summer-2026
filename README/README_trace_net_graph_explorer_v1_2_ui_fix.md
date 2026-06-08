# TRACE-Net Graph Explorer v1.2 UI Fix

Fixes the browser-side graph explorer UI:

- removes fragile inline JavaScript regex escaping for node buttons
- uses data-node-id attributes and event listeners instead
- preserves Decimal JSON serialization support from v1.1
- no database/source/trust/RAG data is mutated

Rebuild the explorer after applying:

```bash
python scripts/build_trace_net_graph_explorer.py --database-url "$TRACE_NET_DATABASE_URL" --open
```
