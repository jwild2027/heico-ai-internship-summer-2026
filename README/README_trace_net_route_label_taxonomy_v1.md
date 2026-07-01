# TRACE-Net Route Label Taxonomy v1

This module locks the canonical page route labels for the OCR/router accuracy loop.

It replaces coarse route thinking like `table` versus `image_visual` with a stricter set of labels:

- `blank_candidate`
- `cover_or_title_page`
- `normal_text`
- `procedure_or_description`
- `table_or_index`
- `detailed_parts_list`
- `image_visual_diagram`
- `mixed_text_and_figure`
- `review_required`

The taxonomy is not an answer generator. It writes local artifacts only and explicitly denies answer permission, source-truth mutation, and live database writes.

## Intended use

Build this taxonomy before route tuning. Later route-tuning modules should map legacy coarse routes into these canonical labels and then compare against a human/gold route review workbook.

## Safety

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission
