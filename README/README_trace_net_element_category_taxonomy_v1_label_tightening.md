# TRACE-Net Element Category Taxonomy v1 Label Tightening

This patch tightens the page category label logic in `trace_net_element_category_taxonomy_v1`.

## Why

The first taxonomy pass correctly categorized TRACE-Net elements, but page labels could be over-broad because operational/search/community signals and weak table/visual route signals sometimes dominated the label.

Example before:

```text
page 1 -> table_parts_diagram_page
```

even though refined Dublin Core said it should be a text/manual page.

## What changed

- `page_category_label` now uses refined public `dc:type` as the strongest signal.
- Weak table/visual signals remain in `secondary_type_signals` and element counts, but do not force broad page labels.
- Added `semantic_dominant_element_families` for content-bearing families that are better inputs to future category-aware Leiden overlays.
- Added `infrastructure_dominant_element_families` to keep operation/search/community counts visible without letting them dominate grouping hints.
- Leiden grouping hints now prefer semantic/content-bearing families before infrastructure families.

## Safety

This remains read-only metadata:

```text
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
source_truth_mutation_allowed = false
```

Categories are still for navigation, review, retrieval, and community grouping only. They do not prove claims or answer questions.
