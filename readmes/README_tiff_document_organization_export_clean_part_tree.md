# Document organization export clean part-tree fix

This patch makes `export_document_organization.py` use the same clean/canonical part filtering as `audit_document_organization.py`.

Before this patch, the organization audit reported the logical/canonical part tree correctly, but the exported `part_tree.json` still used raw `part_mentions` rows. That allowed compound/noisy references such as slash-group parts to appear in UI/API-ready organization files.

After this patch:

- `part_tree.json` uses `part_catalog_clean` / clean catalog keys as the allow-list when available.
- Compound part references are excluded from the exported logical part tree.
- Raw part counts are still preserved in `organization_summary.json` for transparency.
- `page_index.json` also uses the cleaned logical part list for each page.

Expected local sample counts after the patch are closer to the organization audit:

- Logical/canonical distinct parts: about 386
- Logical/canonical part mentions: about 981
- Raw distinct parts seen: about 636
- Raw part mentions seen: about 1409
- Raw mentions excluded from logical part tree: about 428

Run:

```bash
python -m pytest tests/unit/test_tiff_document_organization_export.py -q
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml
python scripts/check_pipeline_quality.py --require-incremental-smoke
python scripts/show_pipeline_status.py
```
