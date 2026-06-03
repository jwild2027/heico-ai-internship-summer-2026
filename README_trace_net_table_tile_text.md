# TRACE-Net table tile text extractor v1

This patch adds the first text extraction executor after TRACE-Net table crop/tile.
It reads the tile images/manifest created by `run_trace_net_table_tiles.py` and writes table-tile text records under:

```text
local_data/organization/table_extraction/table_tile_text/
```

## Providers

```text
page_ocr   dependency-free baseline; maps existing page OCR lines onto tile bands
mock       deterministic smoke-test provider
planned    planning/no-extraction provider
```

`page_ocr` is intentionally conservative. It does not claim true cell OCR; it gives a fast baseline so TRACE-Net can compare tile-route text signals with existing OCR before heavier engines are added.

## Run

```bash
python scripts/run_trace_net_table_tile_text.py \
  --provider page_ocr \
  --max-tiles 60 \
  --open
```

Then quality:

```bash
python scripts/check_trace_net_table_tile_text_quality.py \
  --write-json \
  --min-records 60 \
  --min-ok-records 1 \
  --max-error-records 0
```

For a dependency-free smoke test:

```bash
python scripts/run_trace_net_table_tile_text.py --provider mock --max-tiles 10 --open
python scripts/check_trace_net_table_tile_text_quality.py --write-json --min-records 10 --min-ok-records 10 --max-error-records 0 --min-part-number-records 1
```

## Outputs

```text
table_tile_text_records.jsonl
table_tile_text_summary.json
table_tile_text_corpus.md
table_tile_text_review.html
table_tile_text_graph_nodes.json
table_tile_text_graph_edges.json
table_tile_text_quality.json
```

## Next step

Use these records to build row candidates and table-extraction trust traits:

```text
tile text -> part-number validation -> row candidates -> trust:table_extraction:A/B/C/D
```
