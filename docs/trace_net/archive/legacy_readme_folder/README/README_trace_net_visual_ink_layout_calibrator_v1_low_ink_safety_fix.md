# TRACE-Net Visual Ink Layout Calibrator v1 Low-Ink Safety Fix

This patch keeps ink/layout detection as a route-only signal, not source truth.

## Change

Low ink no longer automatically means a page is confirmed blank.  The calibrator now separates:

- `ink_blank_candidate`: the image has very little ink or was flagged blank by image recognition.
- `source_confirmed_blank`: TRACE-Net confirms the page is blank only if low ink also has no OCR/source-text support, no verified part/table support, and no meaningful context.
- `sparse_ink_text_or_source_trace`: low-ink pages that still have OCR/source/context evidence are preserved and routed for validation.

## Safety rule

Ink detection can route pages, but it cannot prove blankness or source truth by itself.

A sparse page can still contain useful title, revision, callout, or part information, so these pages are routed through OCR/source/context validation instead of being treated as blank.

## Run

```bash
python -m pytest \
  tests/unit/test_trace_net_visual_ink_layout_calibrator_v1.py \
  tests/unit/test_trace_net_visual_ink_layout_calibrator_v1_quality.py \
  tests/unit/test_trace_net_visual_ink_layout_calibrator_v1_script_imports.py \
  -q
```

Then rerun the Step 16.1 build command.
