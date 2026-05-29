# Document Graph Traversal NameError Fix

Fixes a regression in `tiff/document_graph_traversal.py` where the traversal
renderer called `_node_prop()` but the helper was not defined in the merged
traceability/traversal module.

The failure looked like:

```text
NameError: name '_node_prop' is not defined
```

This patch adds compatibility helpers:

- `_props()`
- `_node_prop()`
- `_node_text()`

and makes the page-context summary renderer robust across graph export shapes.

## Recommended validation

```bash
python -m pytest tests/unit/test_tiff_document_graph_traversal.py tests/unit/test_tiff_document_graph_traceability.py tests/unit/test_tiff_user_query_tests.py -q
python scripts/test_document_graph_traversal.py --part 120-37313-001 --strict --write-json
python scripts/run_user_query_tests.py --config local_config.yaml --write-json
```
