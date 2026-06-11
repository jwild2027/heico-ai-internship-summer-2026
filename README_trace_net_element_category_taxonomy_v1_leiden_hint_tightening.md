# TRACE-Net Element Category Taxonomy v1 - Leiden Hint Tightening

This patch keeps the existing element category labels and counts, but tightens the future Leiden grouping hints.

## Why

After label tightening, page labels were clean, but text pages could still emit Leiden hints for weak table or visual signals. That could pull text/front-matter pages into table/diagram communities when building a future category-aware Leiden overlay.

## Change

The page-local Leiden hint families now use refined `dc:type` as the strongest signal:

- `text_page` hints source/text/citation/evidence/context/review only.
- `blank_page` hints blank/source/citation/review only.
- `table_page` can hint table.
- `visual_page` or `diagram_page` can hint visual/diagram/chart.
- `parts_page` can hint part.

Weak table/visual route signals are still preserved in counts and `secondary_type_signals`, but they are suppressed from `leiden_grouping_hints` unless the refined page type supports them.

## Safety

The taxonomy remains navigation/retrieval/review metadata only:

- no direct answers
- no claim proof
- no source-truth mutation
- no Postgres/Qdrant/OpenSearch writes

## New summary fields

- `leiden_hint_suppressed_family_counts`
- `pages_with_suppressed_leiden_hints`
- `table_hint_without_table_type_count`
- `visual_hint_without_visual_type_count`
- `leiden_hint_tightening_policy`

Expected for the current corpus after rerun:

- text pages should not emit table/visual Leiden hints from weak signals
- true table/diagram/parts pages should keep those hints
