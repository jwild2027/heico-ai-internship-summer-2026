# TRACE-Net Visual Callout Table Linker v1 — B2 Repair

This focused Patch B2 repairs the visual linker after the first real LLaVA run produced only LOW, LLaVA-only records.

What changed:

- Stops splitting stringified LLaVA dictionaries into fake figure/callout fragments.
- Filters prompt echoes and dimension-like values from visual candidate tokens.
- Parses explicit FIG/ITEM text from visual summaries, visible text, and OCR page text when available.
- Synthesizes trusted row-level evidence from `table_route_evidence_packager` by grouping values by `page_id + table_id + row_index`.
- Allows MEDIUM links only when a visual callout matches a unique trusted same-page or nearby-page row. Ambiguous matches remain LOW.

Authority rule remains unchanged: LLaVA sees; OCR/table/figure-item evidence proves; TRACE-Net gates; no answer permission is granted by this module.
