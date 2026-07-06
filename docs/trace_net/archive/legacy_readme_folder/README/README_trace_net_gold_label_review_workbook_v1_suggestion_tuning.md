# TRACE-Net Gold Label Review Workbook v1 Suggestion Tuning

This focused patch tightens the canonical route suggestion logic used by the gold-label review workbook.

## Purpose

The first workbook pass over-corrected from the legacy `table` route into `image_visual_diagram` because generic IPL words such as `figure`, `item`, and `illustrated parts list` appeared on many parts-list/table pages. This patch makes the suggester conservative:

- `detailed_parts_list` wins when part-number density or IPL column terms are present.
- `table_or_index` wins for LEP, contents, vendor/index, revision, page/date, and column-heavy pages.
- `image_visual_diagram` requires concrete diagram labels/captions and limited text, or the legacy image route.
- `procedure_or_description` and `mixed_text_and_figure` handle prose pages without forcing them into table.
- `cover_or_title_page` remains a high-confidence front-matter label for page 1/title pages.

## Safety

This patch writes review artifacts only. It does not write to Postgres, Qdrant, or OpenSearch. It does not mutate source truth and does not grant answer permission.
