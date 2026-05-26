# TIFF Search Click-Through HTML

This add-on creates a local HTML page with the top search results. Each result has clickable links for the TIFF page and OCR text file.

It is meant for quick review of the first 10 results from the local search catalog.

## Example

```bash
python scripts/export_tiff_search_html.py "T.P. 120/1176" --limit 10 --open
```

For part-number testing:

```bash
python scripts/export_tiff_search_html.py "120-50648-533" --mode part --limit 10 --open
```

Output defaults to:

```text
local_data/search_results/last_search.html
```

The HTML page is local-only. It does not start a server and does not upload files anywhere.
