# TIFF Document Graph Traceability

This patch adds a read-only traceability layer for the exported document graph.
It helps prove how a user-facing result is connected back to source evidence.

## What it tests

Typical trace paths:

```text
Part -> Page -> SourceLink -> PageContext
Page -> Document / ATA / Parts / SourceLink / PageContext
ATA -> Pages -> SourceLink / PageContext
Qdrant hit payload -> Page -> SourceLink / PageContext / Parts
```

The Qdrant path is represented by `--vector-page` for now. In production,
Qdrant should return payload fields such as `chunk_id` and `page_id`; the
backend then resolves that `page_id` through the PostgreSQL graph/catalog.

## Run tests

```bash
python -m pytest tests/unit/test_tiff_document_graph_traceability.py -q
```

## Trace a part

```bash
python scripts/trace_document_graph.py --part 120-37313-001 --strict --write-json
```

## Trace one page

```bash
python scripts/trace_document_graph.py --page t_p_120_1176_p000083 --strict --write-json
```

## Trace an ATA section

```bash
python scripts/trace_document_graph.py --ata 25-21-00 --max-pages 8 --strict --write-json
```

## Simulate Qdrant -> graph traversal

```bash
python scripts/trace_document_graph.py --vector-page t_p_120_1176_p000495 --vector-chunk chunk_t_p_120_1176_p000495_001 --vector-score 0.635 --strict --write-json
```

The vector trace demonstrates the intended production handoff:

```text
Qdrant returns chunk_id + page_id
    -> backend resolves page_id through graph/PostgreSQL
    -> page links to document, ATA, source link, page context, and parts
```

## Files read

```text
local_data/organization/graph/graph_nodes.json
local_data/organization/graph/graph_edges.json
```

## Files written

Only when `--write-json` is passed:

```text
local_data/organization/graph/traceability_report.json
```
