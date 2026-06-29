# TRACE-Net Answer Context Graph/Leiden Expander v1

Adds graph/Leiden context to enriched answer evidence for final prompt construction.

This fix updates the expander to join graph/community artifacts through multiple keys instead of only top-level `records` page IDs. It supports `nodes`, `graph_nodes`, `community_assignments`, page IDs, page numbers, and TIFF source members. Graph/Leiden context is used only to rank/expand nearby evidence and never grants answer permission or source-truth proof.

Safety contract: dry-run only; no Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, no answer permission.
