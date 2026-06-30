# TRACE-Net Table Row Context Source Expander v1

Builds row-context evidence for visual-linked part numbers by walking back from image visual evidence into table evidence rows and optional upstream artifacts.

## G2B strict nomenclature filter

This revision keeps the G2 row-context expansion behavior, but tightens nomenclature selection:

- Rejects graph/community labels such as `Table + parts + diagram review community`, `Visual part / diagram review community`, and `Part family community ...`.
- Rejects Dublin Core page titles such as `TRACE-Net page 315`.
- Rejects metadata booleans and `trace_net:*` fields.
- Accepts only official-looking fields such as `description`, `nomenclature`, `part_description`, `item_description`, `ipl_text`, `part_name`, or `item_name`.
- Keeps rejected candidates in the artifact for audit instead of silently dropping them.

This module is retrieval/audit only. It does not grant answer permission and does not write to Postgres, Qdrant, or OpenSearch.
