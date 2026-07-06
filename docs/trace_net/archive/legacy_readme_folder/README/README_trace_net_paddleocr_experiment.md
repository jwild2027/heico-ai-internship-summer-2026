# TRACE-Net PaddleOCR Table-Tile Experiment

This patch adds an experiment layer for testing PaddleOCR / PP-StructureV3 on the table tile images produced by TRACE-Net's table crop/tile executor.

It does not replace core graph, OCR, RAG, or trust-trait artifacts. It writes a separate experiment output directory:

```text
local_data/organization/table_extraction/paddleocr_experiment/
```

## Files added

```text
tiff/trace_net_paddleocr_experiment.py
scripts/run_trace_net_paddleocr_table_experiment.py
scripts/check_trace_net_paddleocr_table_quality.py
tests/unit/test_tiff_trace_net_paddleocr_experiment.py
tests/unit/test_tiff_trace_net_paddleocr_quality.py
README_trace_net_paddleocr_experiment.md
```

## Test

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_paddleocr_experiment.py \
  tests/unit/test_tiff_trace_net_paddleocr_quality.py \
  -q
```

## Safe smoke test without PaddleOCR

```bash
python scripts/run_trace_net_paddleocr_table_experiment.py \
  --provider planned \
  --max-tiles 10
```

Mock test:

```bash
python scripts/run_trace_net_paddleocr_table_experiment.py \
  --provider mock \
  --max-tiles 10 \
  --open
```

Quality check:

```bash
python scripts/check_trace_net_paddleocr_table_quality.py \
  --write-json \
  --min-records 10 \
  --min-ok-records 10 \
  --max-error-records 0 \
  --min-part-number-records 1
```

## Real PaddleOCR run

Install PaddleOCR/PaddlePaddle according to the PaddleOCR docs for your machine. Then try a tiny run first:

```bash
python scripts/run_trace_net_paddleocr_table_experiment.py \
  --provider paddleocr \
  --max-tiles 5 \
  --lang en \
  --open
```

If you have GPU support configured:

```bash
python scripts/run_trace_net_paddleocr_table_experiment.py \
  --provider paddleocr \
  --device gpu \
  --max-tiles 5 \
  --lang en \
  --open
```

Then scale:

```bash
python scripts/run_trace_net_paddleocr_table_experiment.py \
  --provider paddleocr \
  --max-pages 4 \
  --lang en \
  --open
```

## Outputs

```text
paddleocr_tile_text_records.jsonl
paddleocr_tile_text_summary.json
paddleocr_tile_text_corpus.md
paddleocr_tile_text_review.html
paddleocr_tile_text_graph_nodes.json
paddleocr_tile_text_graph_edges.json
paddleocr_tile_text_quality.json
```

## Notes

PaddleOCR PP-StructureV3 can output OCR, layout blocks, table recognition results, and Markdown. This experiment captures generic text, Markdown, HTML table snippets, cell text, detected part-like strings, and a graph overlay. It is deliberately flexible because PaddleOCR result shapes can differ across versions and settings.
