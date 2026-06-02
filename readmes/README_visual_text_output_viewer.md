# Visual text output viewer

Read-only helper for inspecting the model-generated visual-text extraction output.

Default input files:

```text
local_data/organization/visual_text/visual_text_extraction.jsonl
local_data/organization/visual_text/visual_text_extraction_summary.json
```

## Print the 25-page pilot in the terminal

```bash
python scripts/print_visual_text_outputs.py --limit 25
```

## Print one page with full markdown

```bash
python scripts/print_visual_text_outputs.py \
  --page-id t_p_120_1176_p000009 \
  --full
```

## Search inside the extracted text

```bash
python scripts/print_visual_text_outputs.py --search table --limit 10
python scripts/print_visual_text_outputs.py --search part --limit 10
python scripts/print_visual_text_outputs.py --search callout --limit 10
```

## Build a local review page

```bash
python scripts/print_visual_text_outputs.py \
  --write-md \
  --write-html \
  --open
```

This writes:

```text
local_data/organization/visual_text/visual_text_review.md
local_data/organization/visual_text/visual_text_review.html
```

If opening the local HTML file directly causes browser restrictions, serve the folder:

```bash
python -m http.server 8766 --directory local_data/organization/visual_text
```

Then visit:

```text
http://127.0.0.1:8766/visual_text_review.html
```
