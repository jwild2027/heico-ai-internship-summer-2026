# TRACE-Net Meaningful Image Route Detector v1.2

This patch calibrates v1.1 after contact-sheet and record inspection.

## Why v1.2

v1.1 separated contact sheets, but it over-promoted table/list pages to
`mixed_visual_table`. The problem was that repeated table columns and dense lists
created many small connected components, which looked like callout labels.

v1.2 adds a safer three-tier decision:

```text
image_visual              = confirmed diagram-dominant page
mixed_visual_table        = confirmed visual + table page
visual_candidate_review   = visual-looking but not trusted enough for image route
table                     = table/list/grid-dominant page
review_candidate          = ambiguous
```

Pages that were not already routed as `image_visual` no longer become image route
just because they have many small label-like components. They need stronger
diagram proof, especially figure-text evidence or low table/text dominance.

## Outputs

```text
accepted_diagram_dominant_contact_sheet.png
accepted_mixed_visual_table_contact_sheet.png
visual_candidate_review_contact_sheet.png
old_image_rejected_as_table_contact_sheet.png
old_image_rejected_as_review_contact_sheet.png
new_visual_not_old_route_contact_sheet.png
uncertain_review_contact_sheet.png
route_disagreement_contact_sheet.png
```

## Safety contract

- no Ollama calls
- no LLM calls
- no OCR execution
- no Postgres/Qdrant/OpenSearch writes
- no source-truth mutation
- no answer permission
