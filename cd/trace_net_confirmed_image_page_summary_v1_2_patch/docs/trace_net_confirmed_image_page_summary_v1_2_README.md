# TRACE-Net Confirmed Image Page Summary v1.2

v1.2 fixes the LLaVA merge.

`confirmed_image_page_summary_v1_1` could load LLaVA observations, but it used
the raw LLaVA JSON/fenced text as the subject and visual observation. That
caused cards like:

```text
subject: ```json { "visual_page_type": ...
```

## Fix

v1.2 reads the cleaned LLaVA payload from:

```text
llava_observation_cleaned
```

and uses:

- `diagram_subject_guess`
- `visual_layout_description`
- `figure_title_or_sheet_text_if_clearly_visible`
- `visible_callouts_or_labels_cleaned`
- `visual_uncertainty`

It also filters fake part-number values such as `OCR/TABLE/FIGURE-ITEM`,
`VISUAL/OCR`, `REVIEW-ONLY`, ATA refs like `25-21-00`, and incomplete EMB
fragments like `120-41824-0`.

OCR/table/source evidence remains authority for exact text and exact part facts.
LLaVA remains visual guidance only.
