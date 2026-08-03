# TRACE-Net Confirmed Image LLaVA Observations v1.1

v1.1 tightens the LLaVA prompt after the first 5-page sample.

## Why

The v1 sample was mechanically successful but LLaVA echoed page/header tokens as
callouts:

```text
25, 21, 00, 06, 12, 377
```

It also guessed subjects too strongly on unclear pages.

## Fix

v1.1 prompt rules:

- do not copy hints unless visible in the image
- use `unknown` when the subject is unclear
- do not invent engine/component/support/assembly subjects unless obvious
- keep page headers / ATA / revision / date / page numbers out of callouts
- only list callouts that are attached to arrows, leader lines, bubbles, item markers, or labels

v1.1 also adds deterministic cleanup:

```text
raw LLaVA output preserved
+
llava_observation_cleaned.visible_callouts_or_labels_cleaned
+
llava_observation_cleaned.filtered_out_possible_header_or_boilerplate_labels
```

## Safety

Still visual guidance only. OCR/table/source evidence remains authority for text
and exact part facts.
