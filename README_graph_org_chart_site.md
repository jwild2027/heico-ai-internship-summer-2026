# HEICO interactive graph org-chart site

This patch adds a local static web app for viewing the current TIFF document graph like an interactive organization chart.

The app is built from the generated local artifacts you already have:

```text
local_data/organization/export/*.json
local_data/organization/graph/graph_nodes.json
local_data/organization/graph/graph_edges.json
local_data/organization/entity_traits/page_character_cards.json
local_data/organization/entity_traits/part_character_cards.json
local_data/organization/entity_traits/trait_graph_summary.json
local_data/organization/image_recognition/page_image_recognition_quality.json
local_data/organization/page_visual_object_quality.json
```

It does not mutate the graph. It writes a browser-openable static site under:

```text
local_data/organization/org_chart_site/index.html
```

## Install patch

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026
unzip -o ~/Downloads/heico_graph_org_chart_site.zip -d .
python -m pytest tests/unit/test_tiff_graph_org_chart_site.py tests/unit/test_tiff_current_graph_org_chart_site.py -q -s
```

The local 509-page test prints the output path when your ignored `local_data/` artifacts are present.

## Build the site

```bash
python scripts/build_graph_org_chart_site.py \
  --expect-pages 509 \
  --expect-documents 1
```

Expected shape:

```text
Interactive graph org-chart site
  Status: ok
  Output dir: local_data/organization/org_chart_site
  Corpus:
    documents: 1
    ata_sections: 5
    pages: 509
    parts: 386
    page_part_links: ...
    pages_with_parts: ...
    pages_with_source_url: ...
    pages_with_tiff_path: ...
    pages_with_ocr_path: ...
    pages_with_derived_traits: ...
  Graph:
    graph_nodes: 3788
    graph_edges: 14143
    trait_assertions: 11980
    trait_nodes: 963
  Files written:
    index: local_data/organization/org_chart_site/index.html
    data_json: local_data/organization/org_chart_site/graph_org_chart_data.json
    summary_json: local_data/organization/org_chart_site/graph_org_chart_summary.json
```

## Visit the site

From Git Bash:

```bash
explorer.exe "$(cygpath -w local_data/organization/org_chart_site/index.html)"
```

Or serve it locally:

```bash
python scripts/serve_graph_org_chart_site.py
```

Then visit:

```text
http://127.0.0.1:8765/index.html
```

You can also use Python's built-in server directly:

```bash
python -m http.server 8765 --directory local_data/organization/org_chart_site
```

## What the site shows

The main view is:

```text
Document
  -> ATA Section
      -> Page cards
```

Clicking a page opens a right-side inspector with the page's character-sheet style data:

```text
path: document -> ATA -> page
role
image classes
summary/context
source URL
TIFF path
OCR path
parts
source-backed direct traits
derived traits
signals
```

The toolbar supports:

```text
search by page / part / ATA / source / trait / summary
filter by ATA
filter by page role
filter by derived trait
collapse/show all page cards
zoom
```

## Files added

```text
tiff/graph_org_chart_site.py
scripts/build_graph_org_chart_site.py
scripts/serve_graph_org_chart_site.py
tests/unit/test_tiff_graph_org_chart_site.py
tests/unit/test_tiff_current_graph_org_chart_site.py
README_graph_org_chart_site.md
```
