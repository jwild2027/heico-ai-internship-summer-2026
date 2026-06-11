# TRACE-Net Graph Overlay PartCandidate Page-Lineage v1

**Status:** GRAPH_OVERLAY_PART_LINEAGE_BUILT
**Quality:** PASS
**Writeback mode:** dry_run_lineage_refinement

## Summary

- Pages: 509
- Overlay nodes: 32446
- Overlay edges: 35907
- PartCandidate nodes: 301
- PartCandidate nodes with source pages: 301
- PartCandidate missing source pages: 0
- Page-scoped missing page IDs: 0
- Orphan edges: 0
- Nomenclature edges preserved: 386
- ContextV2 edges preserved: 50

PartCandidate nodes are cross-page bridge entities. They keep `source_page_ids` instead of being forced into a single `page_id`.
This is a dry-run lineage overlay and does not mutate Postgres or source truth.
