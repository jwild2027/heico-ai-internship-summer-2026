# TIFF document organization audit

This patch adds a read-only logical organization audit for the TIFF backend.

It does not move, rename, OCR, index, or modify source files. It reads the
SQLite/source-link/part tables and prints a logical tree summary:

- manuals
- pages
- ATA groups
- pages with/without ATA
- part mentions
- top part-tree entries
- empty OCR pages already visible in the logical tree

Run:

```bash
python scripts/audit_document_organization.py --config local_config.yaml --write-json
```

Useful strict check:

```bash
python scripts/audit_document_organization.py --config local_config.yaml --strict
```

Output JSON defaults to:

```text
local_data/organization/document_organization_audit.json
```

This is the next step toward a logical organization layer over a messy TIFF /
ResCarta server. The raw files can stay where they are; this audit shows whether
our backend can already organize indexed pages by manual, ATA, and part.
