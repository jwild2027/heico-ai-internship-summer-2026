# TIFF document organization export pipeline integration

This patch makes the logical document organization layer both visible and reusable.

It adds the organization export step to the normal backend pipeline after the organization audit and before RAG eval:

```text
source_link_audit
ocr_coverage_audit
document_organization_audit
document_organization_export
rag_eval
```

The export writes UI/API-ready JSON files:

```text
local_data/organization/export/manual_ata_tree.json
local_data/organization/export/ata_tree.json
local_data/organization/export/part_tree.json
local_data/organization/export/page_index.json
local_data/organization/export/organization_summary.json
```

The pipeline manifest, quality gate, and status output now include an organization export summary.

Run:

```bash
python -m pytest tests/unit/test_tiff_document_organization_audit.py tests/unit/test_tiff_document_organization_export.py tests/unit/test_tiff_document_organization_pipeline_quality.py -q
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml
python scripts/check_pipeline_quality.py --require-incremental-smoke
python scripts/show_pipeline_status.py
```

Expected status includes:

```text
Document organization export summary:
  Export ready: True
  Manuals: 1
  Pages: 509
  ATA groups: 5
  Distinct parts: 636
  Part mentions: 1409
  Files written: 5
```
