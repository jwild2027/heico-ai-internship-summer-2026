# Document organization part-tree fix

This patch fixes the logical organization audit so it recognizes the current
backend part mention schema:

- `part_number_display`
- `part_number_normalized`
- `nomenclature_clean`

The earlier audit could organize manuals and ATA groups, but it could report
`Part mentions: 0` even when the SQLite database contained rows in
`part_mentions`. After this patch, the part tree should use the same columns as
the source-link and incremental smoke paths.

Run:

```bash
python -m pytest tests/unit/test_tiff_document_organization_audit.py -q
python scripts/audit_document_organization.py --config local_config.yaml --write-json
```

Expected improvement on the current sample database:

```text
Distinct parts mentioned: > 0
Part mentions: 1409
Pages with parts: > 0
Top part tree entries:
  ...
```
