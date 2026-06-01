# Current graph setup report

This patch adds a read-only graph inspection/report tool for the local TIFF document graph and the entity-trait overlay.

It is designed for the current processed corpus:

```text
1 document
509 pages
509 page contexts
509 source links
386 parts
entity-trait overlay generated from the current graph/image/context artifacts
```

## Files added

```text
tiff/graph_setup_report.py
scripts/print_current_graph_setup.py
tests/unit/test_tiff_graph_setup_report.py
tests/unit/test_tiff_current_graph_setup_report.py
README_current_graph_setup_report.md
```

## Run the tests

Use `-s` so pytest prints the graph report instead of capturing stdout.

```bash
python -m pytest tests/unit/test_tiff_graph_setup_report.py tests/unit/test_tiff_current_graph_setup_report.py -q -s
```

The local-artifact tests skip automatically if `local_data/organization/graph/graph_nodes.json` and `graph_edges.json` are not present. In your current repo, they should run and print the 509-page graph setup.

## Print the report directly

```bash
python scripts/print_current_graph_setup.py --expect-pages 509 --expect-documents 1 --samples 10
```

Optional JSON output:

```bash
python scripts/print_current_graph_setup.py \
  --expect-pages 509 \
  --expect-documents 1 \
  --samples 10 \
  --write-json local_data/organization/entity_traits/current_graph_setup_report.json
```

## What it prints

The report includes:

```text
Processed corpus counts
Core graph node counts
Core graph edge counts
Document distribution
Page coverage checks
ATA distribution
Entity-trait overlay counts
Trait categories
Page image-recognition / visual quality signals
Sample page character sheets
```

The page character-sheet sample shows the current model in the same style as the trait-graph idea:

```text
page -> document parent
page -> ATA parent
page -> source link / TIFF / OCR
page -> page context
page -> parts / part mentions
page -> direct and derived traits
```

This patch does not mutate graph artifacts. It only reads them.
