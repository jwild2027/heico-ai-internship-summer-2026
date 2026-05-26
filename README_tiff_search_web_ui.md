# Local TIFF Search Web UI

This package adds a simple browser-based search page for the local TIFF search catalog.

It is local-only. It uses the SQLite search database you already built and does not send TIFFs, OCR text, or metadata to any external service.

## Included files

```text
scripts/serve_tiff_search_ui.py
scripts/export_tiff_search_csv.py
scripts/export_tiff_search_html.py
scripts/build_tiff_search_index.py
scripts/search_tiffs.py
tiff/search_index.py
tiff/search_results_html.py
tiff/search_web_ui.py
tests/unit/test_tiff_search_index.py
tests/unit/test_tiff_search_results_html.py
tests/unit/test_tiff_search_web_ui.py
```

## Run the web UI

From the project repo:

```bash
python scripts/serve_tiff_search_ui.py --db-path local_data/db/tiff_search.db --host 127.0.0.1 --port 8080 --open
```

Then search in the browser:

```text
http://127.0.0.1:8080
```

Good test searches:

```text
120-37313-001
120-36843-001
120-48023-001
AM03078-22
oxygen bottle bracket
25-21-00
```

## What the web page does

The page lets a user:

```text
search by part number, ATA code, manual number, or keyword
choose auto / part / keyword mode
view the matching TIFF in the browser
open the TIFF in the desktop viewer
view OCR text
copy the TIFF path
export results to CSV
```

## CSV export from command line

```bash
python scripts/export_tiff_search_csv.py "120-37313-001" --db-path local_data/db/tiff_search.db --mode part --limit 25 --output-csv local_data/search_results/part_120-37313-001.csv
```

## Rebuild the search DB

```bash
python scripts/build_tiff_search_index.py --rescarta-export-dir local_data/rescarta_exports --output-db local_data/db/tiff_search.db
```

## Stop the web UI

Press `Ctrl+C` in the terminal running the server.
