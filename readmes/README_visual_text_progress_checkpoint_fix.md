# Visual text extraction progress + checkpoint fix

This patch makes long visual text extraction runs easier to monitor and safer to stop/restart.

## What changed

`scripts/run_visual_text_extraction.py` now prints one progress line after every completed page by default:

```text
Visual text extraction progress: selected_pages=25 provider=ollama model=llava:13b max_image_edge=1024
[1/25] t_p_120_1176_p000001 -> ok chars=799 page_time=1m 12s avg=1m 12s eta=28m 48s
[2/25] t_p_120_1176_p000003 -> ok chars=1011 page_time=1m 26s avg=1m 19s eta=30m 17s
```

It also checkpoint-writes partial outputs after every completed page by default:

```text
local_data/organization/visual_text/visual_text_extraction.jsonl
local_data/organization/visual_text/visual_text_corpus.md
local_data/organization/visual_text/visual_text_graph_nodes.json
local_data/organization/visual_text/visual_text_graph_edges.json
```

The final summary JSON is still written at the end of the run.

## New CLI flags

Disable progress printing:

```bash
--quiet
```

Change checkpoint cadence:

```bash
--checkpoint-every 5
```

Disable checkpoint writes during the loop:

```bash
--checkpoint-every 0
```

## Recommended 25-page run

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:13b \
  --max-pages 25 \
  --overwrite \
  --timeout-seconds 600 \
  --max-image-edge 1024
```

Then quality check:

```bash
python scripts/check_visual_text_extraction_quality.py \
  --write-json \
  --disallow-planned
```
