# TRACE-Net Leiden / Community Overlay

This patch adds a community-detection overlay for TRACE-Net.

It builds a **projected semantic graph** from existing page cards, page index records,
trust traits, table candidates, table tiles, repair routes, parts, roles, image classes,
and ATA sections. It intentionally does **not** run community detection on the raw
source/evidence graph because source/OCR/TIFF edges would distort semantic clusters.

## Install optional Leiden dependency

The pipeline works without Leiden by falling back to NetworkX greedy modularity or
connected components, but real Leiden requires:

```bash
pip install igraph leidenalg
```

Then run with:

```bash
python scripts/plan_trace_net_leiden_communities.py --algorithm leiden --expect-pages 509
```

## Run in auto mode

```bash
python scripts/plan_trace_net_leiden_communities.py \
  --algorithm auto \
  --expect-pages 509 \
  --samples 20
```

If `leidenalg` is installed, this uses Leiden. Otherwise it falls back safely.

## Quality gate

```bash
python scripts/check_trace_net_leiden_quality.py \
  --write-json \
  --min-pages 509 \
  --min-communities 1
```

To require real Leiden:

```bash
python scripts/check_trace_net_leiden_quality.py \
  --write-json \
  --min-pages 509 \
  --min-communities 1 \
  --require-leiden
```

## Outputs

```text
local_data/organization/communities/semantic_projection_nodes.json
local_data/organization/communities/semantic_projection_edges.json
local_data/organization/communities/leiden_communities.json
local_data/organization/communities/leiden_communities.jsonl
local_data/organization/communities/leiden_graph_nodes.json
local_data/organization/communities/leiden_graph_edges.json
local_data/organization/communities/leiden_community_summary.json
local_data/organization/communities/leiden_community_review.md
local_data/organization/communities/leiden_community_quality.json
```

## Intended use

This is an overlay. It should help discover communities like:

- effective page / revision table clusters
- numerical index pages
- table grid / parts list clusters
- figure/diagram clusters
- vendor/reference clusters
- part-family neighborhoods

It does not replace the core source-traceable graph.
