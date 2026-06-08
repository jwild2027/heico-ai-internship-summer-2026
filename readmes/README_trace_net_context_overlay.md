# TRACE-Net PostgreSQL Context Overlay v1

This patch adds a lightweight PostgreSQL overlay for the TRACE-Net architecture and local data summary context.

It is intentionally **not** source evidence. It stores operator/project context such as pipeline stages, route policy, local summary counts, RAG bucket counts, and future indexing rules.

## Files

```text
scripts/load_trace_net_postgres_context_overlay.py
scripts/check_trace_net_postgres_context_overlay_quality.py
tiff/trace_net_postgres_context_overlay.py
local_data/organization/trace_net/context_overlay/trace_net_context_seed.json
tests/unit/test_trace_net_postgres_context_overlay.py
```

## Tables

```text
trace_net_context_overlay_snapshots
trace_net_context_overlay_items
trace_net_context_overlay_edges
trace_net_context_overlay_metrics
```

Every row is marked:

```text
authority_scope = project_context_only
answer_authority = none
```

That makes the overlay safe to use for architecture memory, admin UI, retrieval planning, and QA, while preventing it from becoming direct manual answer evidence.

## Load

Set your local Postgres DSN:

```bash
export TRACE_NET_PG_DSN="postgresql://postgres:postgres@localhost:5432/trace_net"
```

Dry run first:

```bash
python scripts/load_trace_net_postgres_context_overlay.py --dry-run
```

Load to Postgres:

```bash
python scripts/load_trace_net_postgres_context_overlay.py
```

Check quality:

```bash
python scripts/check_trace_net_postgres_context_overlay_quality.py \
  --snapshot-id trace_net_context_overlay:current_architecture_v1
```

## Expected seed counts

```text
items:   35
edges:   39
metrics: 12
```

## Design rule

This overlay is for project/operator context only. It must not mutate source truth, evidence consensus, trust authority, Stage 5b decisions, RAG eligibility, citations, or feedback policy.
