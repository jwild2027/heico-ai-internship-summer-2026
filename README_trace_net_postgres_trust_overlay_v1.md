# TRACE-Net Postgres Trust Overlay v1

This package adds a read/safe normalization layer for trust tiers inside the local
PostgreSQL test backend.

It does not change source truth, RAG eligibility, production ranking, or feedback.
It only:

1. normalizes `rag_candidate_chunks.trust_tier`,
2. creates `evidence_trust_records`,
3. creates `page_trust_traits`,
4. writes JSON/HTML graph/report artifacts,
5. provides a quality gate.

## Run

```bash
python scripts/build_trace_net_postgres_trust_overlay.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --open
```

## Quality

```bash
python scripts/check_trace_net_postgres_trust_overlay_quality.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --write-json \
  --min-pages 509 \
  --min-trust-records 1426 \
  --min-page-trust-traits 509 \
  --min-pages-with-trust-traits 509 \
  --min-source-trace-A-records 509 \
  --min-source-text-A-records 495 \
  --min-verified-part-A-records 360 \
  --min-derived-context-records 60 \
  --max-missing-candidate-trust-tier 0 \
  --max-unsafe-trusted-rag-records 0 \
  --max-source-truth-mutations 0
```

## Outputs

```text
local_data/organization/trace_net/trust_overlay/trace_net_postgres_trust_overlay_summary.json
local_data/organization/trace_net/trust_overlay/trace_net_postgres_trust_overlay_records.jsonl
local_data/organization/trace_net/trust_overlay/trace_net_postgres_trust_overlay_report.html
local_data/organization/trace_net/trust_overlay/trace_net_postgres_trust_overlay_graph_nodes.json
local_data/organization/trace_net/trust_overlay/trace_net_postgres_trust_overlay_graph_edges.json
local_data/organization/trace_net/trust_overlay/trace_net_postgres_trust_overlay_quality.json
```
