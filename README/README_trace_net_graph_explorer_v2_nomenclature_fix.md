# TRACE-Net Graph Explorer v2/Nomenclature Fix

This patch adds a read-only graph explorer overlay builder that makes both of these paths visible in the local HTML graph UI:

```text
Part -> HAS_NOMENCLATURE -> Nomenclature
Page 000001-000050 -> HAS_CONTEXT_V2 -> PageContextV2
```

The PageContextV2 nodes are treated as retrieval guidance only. They are quick query tunnels for routing/search, not source truth and not answer authority.

## Files

```text
scripts/build_trace_net_graph_explorer_v2_nomenclature_fix.py
scripts/check_trace_net_graph_explorer_v2_nomenclature_fix_quality.py
tests/unit/test_trace_net_graph_explorer_v2_nomenclature_fix.py
tests/unit/test_trace_net_graph_explorer_v2_nomenclature_quality.py
README_trace_net_graph_explorer_v2_nomenclature_fix.md
```

## Build

```bash
export TRACE_NET_DATABASE_URL="postgresql://tracenet:tracenet@localhost:5432/tracenet_dev"

python scripts/build_trace_net_graph_explorer_v2_nomenclature_fix.py \
  --database-url "$TRACE_NET_DATABASE_URL" \
  --require-first-pages 1-50 \
  --open
```

## Quality check

```bash
python scripts/check_trace_net_graph_explorer_v2_nomenclature_fix_quality.py \
  --output-dir local_data/organization/trace_net/graph_explorer \
  --min-page-nodes 509 \
  --min-nomenclature-nodes 1 \
  --min-has-nomenclature-edges 1 \
  --min-context-v2-pages 50 \
  --require-first-pages 1-50 \
  --write-json
```

## Outputs

```text
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer.html
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_data.json
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_summary.json
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_nodes.json
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_edges.json
local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_v2_nomenclature_quality.json
```

## Safety notes

This patch does not mutate Postgres. It only reads existing graph/evidence/context rows and writes local UI JSON/HTML artifacts.

TRACE-Net rule preserved:

```text
PageContextV2 can guide retrieval.
PageContextV2 cannot prove an answer.
Final answer authority must still come from source/citation/trust gates.
```
