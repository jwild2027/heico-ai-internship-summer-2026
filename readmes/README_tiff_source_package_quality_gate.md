# TIFF source-package traceability quality gate

This patch adds an official quality check for the raw source package to processed organization traceability.

It validates the report produced by:

```bash
python scripts/audit_source_package_traceability.py \
  --zip /c/Users/juswil/Documents/00000027/metadata.zip \
  --write-json
```

The new check verifies:

- the traceability report exists
- the source ZIP has TIFF pages
- `metadata.xml` is present
- ZIP TIFF pages match organization pages by normalized page number
- there are no ZIP-only or organization-only pages
- there are no duplicate normalized page numbers
- organization pages have TIFF paths

## Run

```bash
python -m pytest tests/unit/test_tiff_source_package_quality.py -q

python scripts/audit_source_package_traceability.py \
  --zip /c/Users/juswil/Documents/00000027/metadata.zip \
  --write-json

python scripts/check_source_package_quality.py --write-json
python scripts/refresh_source_package_quality_summary.py

python scripts/check_pipeline_quality.py \
  --require-incremental-smoke \
  --require-user-query-tests \
  --require-realistic-query-trace \
  --require-slow-realistic-query-trace \
  --require-source-package-traceability
```

## Meaning

This protects the key trust chain:

```text
raw source ZIP TIFF page
  -> organization page
  -> graph page node
  -> source link
  -> AI context / parts / RAG evidence
```

The check is read-only. It does not OCR, mutate the graph, or rebuild the backend.
