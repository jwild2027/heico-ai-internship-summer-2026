# Document organization query cleanup

This patch tightens the user-style organization query helper.

Fixes:

- ATA queries now collect only top-level ATA groups, not every nested page row with an ATA code.
- Query summary reads `ata_group_count`, `part_count`, and `part_mention_count` from `organization_summary.json`.
- ATA output uses `distinct_part_count` / `part_mention_count` instead of showing `parts=0` when the group is populated.
- Page output recognizes `ocr_text_path`, so user page lookup prints the OCR path.
- Part/page collection prefers top-level exported collections instead of fully recursive collection.

Run:

```bash
python -m pytest tests/unit/test_tiff_document_organization_query.py -q
python scripts/query_document_organization.py --part 120-37313-001 --part AM03078-22 --ata 25-21-00 --page t_p_120_1176_p000042 --strict
```
