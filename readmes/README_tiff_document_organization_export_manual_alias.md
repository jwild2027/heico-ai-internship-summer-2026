# Document organization export manual aliases

This patch makes the exported organization JSON easier for a future UI/API to
consume by adding simple alias fields alongside the backend canonical fields.

## What changes

- `manual_ata_tree.json` manual entries include `manual` and `title` aliases.
- `ata_tree.json` ATA group entries include `manual` and `ata` aliases.
- `page_index.json` page entries include `manual` and `ata` aliases.
- `inspect_document_organization_export.py` now recognizes `publication_number`
  and `manual_id` when displaying ATA/page samples.

The canonical backend fields remain available:

- `manual_id`
- `publication_number`
- `ata_code`

## Run

```bash
python -m pytest tests/unit/test_tiff_document_organization_export.py tests/unit/test_tiff_document_organization_inspector.py -q
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml
python scripts/inspect_document_organization_export.py --strict --part 120-37313-001 --part AM03078-22 --ata 25-21-00 --write-json
```
