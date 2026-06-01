# Page visual/object audit graph-linkage fix

Fixes `audit_page_visual_objects.py` showing graph linkage counts as zero when `graph_summary.json` uses a nested or alternate summary shape.

Run:

```bash
python scripts/apply_page_visual_graph_linkage_fix.py
python -m pytest tests/unit/test_tiff_page_visual_object_audit.py tests/unit/test_tiff_page_visual_object_graph_linkage.py -q
python scripts/audit_page_visual_objects.py --write-json
```

Expected graph linkage after the fix:

```text
page_context nodes: 509
HAS_CONTEXT edges: 509
TAGGED_AS edges: 1706
HIGHLIGHTS_PART edges: 1070
```
