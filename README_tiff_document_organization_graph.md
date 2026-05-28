# TIFF Document Organization Graph Export

This patch adds a read-only graph export layer on top of the existing document organization export.

It reads:

```text
local_data/organization/export/manual_ata_tree.json
local_data/organization/export/ata_tree.json
local_data/organization/export/part_tree.json
local_data/organization/export/page_index.json
local_data/organization/export/organization_summary.json
```

and writes:

```text
local_data/organization/graph/graph_nodes.json
local_data/organization/graph/graph_edges.json
local_data/organization/graph/graph_summary.json
```

## Why this exists

The existing organization export is already useful for UI/API browsing. The graph export makes the relationships explicit:

```text
document HAS_PAGE page
page BELONGS_TO_ATA ata_section
page HAS_TIFF source_file
page HAS_OCR source_file
page MENTIONS_PART part
part HAS_MENTION part_mention
part APPEARS_ON page
page HAS_SOURCE_LINK source_link
source_link OPENS page
```

This helps model the digital library as a graph without introducing a graph database yet.

## Run

```bash
python scripts/export_document_organization_graph.py --strict
```

## Test

```bash
python -m pytest tests/unit/test_tiff_document_organization_graph.py -q
```

## Notes

This command is read-only with respect to the database and source files. It only writes JSON graph artifacts under `local_data/organization/graph/`.
