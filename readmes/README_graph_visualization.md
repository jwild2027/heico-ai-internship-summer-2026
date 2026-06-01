# Current graph visualizations

This patch adds a read-only visualizer for the current HEICO TIFF document graph and the entity-trait overlay.

It does **not** modify graph data. It reads existing artifacts and writes standalone HTML files that can be opened locally in a browser.

## What it shows

The visualizer creates four files:

```text
local_data/organization/visualizations/index.html
local_data/organization/visualizations/page_grid.html
local_data/organization/visualizations/trait_overlay.html
local_data/organization/visualizations/neighborhoods.html
```

### `index.html`

High-level architecture view:

```text
Document -> ATA section -> Page -> Evidence -> Traits
```

It also shows counts for documents, ATA sections, pages, parts, core graph nodes/edges, trait assertions, and role/image distributions.

### `page_grid.html`

A 509-page visual grid. Each tile is a page character sheet.

You can filter by:

```text
ATA section
page role
derived trait
free-text search
```

Click a tile to inspect:

```text
page id
document
ATA code
role
image classification
source URL
TIFF path
OCR path
parts
topics
direct traits
derived traits
summary
```

### `trait_overlay.html`

Trait/assertion summary for the game-character style overlay:

```text
Entity -> HAS_TRAIT_ASSERTION -> TraitAssertion -> ASSERTS_TRAIT -> Trait
                                      |
                                      v
                                EvidenceSource
```

### `neighborhoods.html`

Focused page-neighborhood cards:

```text
Parents -> Page -> Evidence -> Parts/Context -> Traits
```

This is usually the best visual shape for demos and debugging. Rendering all 10k+ trait/assertion nodes at once is usually a hairball, so the visualizer favors focused graph views.

## Run

After applying the zip and generating the entity-trait overlay:

```bash
python scripts/export_entity_trait_graph.py
python scripts/visualize_current_graph.py --expect-pages 509 --expect-documents 1 --samples 12
```

The script will print the path to open, usually:

```text
local_data/organization/visualizations/index.html
```

## Tests

Fixture tests:

```bash
python -m pytest tests/unit/test_tiff_graph_visualization.py -q
```

Current local 509-page graph test with printed output:

```bash
python -m pytest tests/unit/test_tiff_current_graph_visualization.py -q -s
```

This test skips if the ignored `local_data` artifacts are not present.

## Added files

```text
tiff/graph_visualization.py
scripts/visualize_current_graph.py
tests/unit/test_tiff_graph_visualization.py
tests/unit/test_tiff_current_graph_visualization.py
README_graph_visualization.md
```
