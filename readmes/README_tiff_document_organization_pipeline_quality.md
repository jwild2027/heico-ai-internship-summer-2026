# Document organization pipeline/status/quality integration

This patch makes the logical document organization audit part of the normal TIFF backend health checks.

## Adds/updates

- `tiff/document_organization_audit.py`
- `scripts/audit_document_organization.py`
- `tiff/pipeline_runner.py`
- `tiff/pipeline_manifest.py`
- `tiff/pipeline_quality.py`
- `scripts/run_tiff_backend_pipeline.py`
- `scripts/check_pipeline_quality.py`
- `tests/unit/test_tiff_document_organization_audit.py`
- `tests/unit/test_tiff_document_organization_pipeline_quality.py`

## New pipeline step

The normal backend pipeline now includes:

```text
document_organization_audit
```

The full pipeline order becomes:

```text
1. search_index
2. part_catalog
3. rag_chunks
4. rag_embeddings
5. part_catalog_qa
6. part_catalog_qa_triage
7. source_link_audit
8. ocr_coverage_audit
9. document_organization_audit
10. rag_eval
```

## What it checks

The organization audit verifies that the backend can build a logical tree over the indexed pages:

```text
manual
  ATA section
    pages
      part mentions
```

It checks counts such as:

- manuals
- pages
- source links
- ATA groups
- pages without ATA
- distinct parts mentioned
- part mentions
- pages with parts
- empty OCR pages in the tree

## Quality gate behavior

The quality gate now checks that:

- `document_organization_audit` is present in the manifest steps
- the document organization summary exists
- the logical tree is ready
- at least one manual exists
- at least one ATA group exists
- pages without ATA are within threshold
- source-link coverage is complete
- the part tree is populated

Default thresholds are local-MVP friendly:

```text
max_document_pages_without_ata = 0
min_document_ata_groups = 1
min_document_distinct_parts = 1
```

These can be changed with:

```bash
python scripts/check_pipeline_quality.py --max-document-pages-without-ata 10 --min-document-distinct-parts 1
```

## Run

```bash
python -m pytest tests/unit/test_tiff_document_organization_audit.py tests/unit/test_tiff_document_organization_pipeline_quality.py -q
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml
python scripts/check_pipeline_quality.py --require-incremental-smoke
python scripts/show_pipeline_status.py
```
