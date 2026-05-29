# TIFF Document Graph Traversal Test

This read-only helper validates useful traversal paths in the exported document organization graph.

It loads:

```text
local_data/organization/graph/graph_nodes.json
local_data/organization/graph/graph_edges.json
```

and proves paths such as:

```text
Document -> Page -> Part -> Nomenclature
Page -> PageContext
Part -> Page -> PageContext / SourceLink
```

## Run

```bash
python -m pytest tests/unit/test_tiff_document_graph_traversal.py -q
python scripts/test_document_graph_traversal.py --part 120-37313-001 --strict --write-json
```

Optional explicit page:

```bash
python scripts/test_document_graph_traversal.py --page t_p_120_1176_p000083 --part 120-37313-001 --strict --write-json
```

The helper does not modify OCR, TIFFs, SQLite/Postgres, graph exports, or context files.
