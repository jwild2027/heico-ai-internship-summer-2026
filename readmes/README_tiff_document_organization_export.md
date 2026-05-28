# TIFF document organization export

This patch adds a read-only export step for the logical organization layer.

It writes JSON artifacts that a future API/UI can consume:

- `manual_ata_tree.json`
- `ata_tree.json`
- `part_tree.json`
- `page_index.json`
- `organization_summary.json`

The export does not move files, rename files, OCR pages, rebuild indexes, or mutate the SQLite database. It only reads the current backend database and writes logical organization JSON.

Run:

```bash
python scripts/export_document_organization.py --config local_config.yaml --strict
```

Default output:

```text
local_data/organization/export/
```

This is the first step from an audit-only logical tree toward UI/API-ready organization data.
