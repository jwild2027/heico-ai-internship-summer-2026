# TIFF ResCarta / Source-Link Mapping

This add-on finishes the backend side of Goal 2: every indexed page can now have a stable source-link row.

It does not require native ResCarta import to be finished. It works with the current ResCarta staging export and stores:

- manual ID
- publication number
- ATA code
- page sequence / page label
- TIFF path
- OCR path
- ResCarta object ID
- ResCarta page ID
- optional ResCarta URL
- source URL fallback

## Build the mapping

```bash
python scripts/build_rescarta_mapping.py --config local_config.yaml --write-report
```

This creates/rebuilds the SQLite table:

```text
source_links
```

and optionally writes:

```text
local_data/source_links/rescarta_mapping_report.csv
local_data/source_links/rescarta_mapping_report.json
local_data/source_links/rescarta_mapping_report.html
```

## Optional ResCarta URL template

When you know the final ResCarta deep-link URL format, pass it as a template:

```bash
python scripts/build_rescarta_mapping.py \
  --config local_config.yaml \
  --rescarta-url-template "http://localhost:8080/rescarta/{object_id}/{page_id}" \
  --write-report
```

Available fields include:

```text
{manual_id}
{object_id}
{page_id}
{page_record_id}
{page_sequence}
{page_label}
{ata_code}
{publication_number}
```

You can also add this to `local_config.yaml`:

```yaml
rescarta_url_template: http://localhost:8080/rescarta/{object_id}/{page_id}
```

## Report mapping coverage

```bash
python scripts/report_rescarta_mapping.py --config local_config.yaml
```

## Resolve one source

```bash
python scripts/resolve_source_link.py --config local_config.yaml 120-37313-001
```

or:

```bash
python scripts/resolve_source_link.py --config local_config.yaml t_p_120_1176_p000083
```

## Recommended order

Run this after the search index is built:

```bash
python scripts/build_tiff_search_index.py --rescarta-export-dir local_data/rescarta_exports --output-db local_data/db/tiff_search.db
python scripts/build_rescarta_mapping.py --config local_config.yaml --write-report
```

Then the source-link table can be used by RAG, reports, UI, and future ResCarta deep links.
