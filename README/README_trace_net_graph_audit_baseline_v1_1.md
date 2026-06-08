# TRACE-Net Graph Audit + Baseline v1.1

Patch for v1 graph audit package.

Fixes:

- `check_trace_net_graph_audit_quality.py` no longer crashes when `--max-pages-without-graph-node` is omitted.
- Page graph-node detection is more tolerant of mixed graph node ID/payload conventions.
- Page-node coverage remains optional unless you explicitly pass `--max-pages-without-graph-node`.

Recommended graph quality command for the current Postgres load:

```bash
python scripts/check_trace_net_graph_audit_quality.py \
  --write-json \
  --min-pages 509 \
  --min-graph-nodes 1 \
  --min-graph-edges 1 \
  --max-orphan-edges 0 \
  --max-rag-candidates-without-page 0 \
  --max-citations-without-page 0 \
  --max-unsafe-rag-candidates 0 \
  --max-missing-candidate-source-url 0
```

Do not enforce candidate trust-tier columns yet. Use a later trust overlay/normalization step.
