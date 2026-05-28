# Document organization query helper

This patch adds a small CLI/API-style reader for the organization JSON export.
It reads `local_data/organization/export` directly, not SQLite.

## Run

```bash
python scripts/query_document_organization.py --part 120-37313-001 --part AM03078-22 --ata 25-21-00 --page t_p_120_1176_p000042 --strict
```

## Why

The organization export is meant to be UI/API-ready. This command proves a consumer can query:

- parts from `part_tree.json`
- ATA groups from `ata_tree.json`
- pages from `page_index.json`
- counts from `organization_summary.json`

without knowing the internal database tables.
