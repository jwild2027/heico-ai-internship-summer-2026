# TIFF Part Catalog / Nomenclature Extractor

This add-on upgrades the local TIFF search system from:

```text
Where does this part number appear?
```

to:

```text
What is this part number, and where is the source TIFF page?
```

Example target result:

```text
Part number: 120-37313-001
Nomenclature: MAGAZINE HOLDER
Manual: T.P. 120/1176
ATA: 25-21-00
Page: 1311
Open TIFF / Open OCR
```

## What it adds

```text
tiff/part_catalog.py
scripts/build_part_catalog.py
scripts/report_part_catalog.py
scripts/search_part_catalog.py
scripts/export_part_catalog_csv.py
tests/unit/test_tiff_part_catalog.py
```

It also updates the existing search command, click-through HTML, CSV export, and local web UI so part-number search results can show:

```text
Nomenclature
Item number
Quantity
Figure number
Confidence
Evidence text
```

## Workflow

Run the search index first, then build the part catalog:

```bash
python scripts/build_tiff_search_index.py --rescarta-export-dir local_data/rescarta_exports --output-db local_data/db/tiff_search.db
python scripts/build_part_catalog.py --db-path local_data/db/tiff_search.db
```

Then search normally:

```bash
python scripts/search_tiffs.py --db-path local_data/db/tiff_search.db "120-37313-001" --mode part --limit 10
```

Or open the web UI:

```bash
python scripts/serve_tiff_search_ui.py --db-path local_data/db/tiff_search.db --host 127.0.0.1 --port 8080 --open
```

## QA helpers

```bash
python scripts/report_part_catalog.py --db-path local_data/db/tiff_search.db --limit 30
python scripts/search_part_catalog.py --db-path local_data/db/tiff_search.db "MAGAZINE HOLDER"
python scripts/export_part_catalog_csv.py --db-path local_data/db/tiff_search.db --output-csv local_data/search_results/part_catalog.csv
```

## Important note

This extractor is source-backed. It only displays nomenclature when it finds OCR evidence near the part number. It does not guess with an LLM.
