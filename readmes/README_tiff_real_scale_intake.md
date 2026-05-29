# TIFF real-scale intake and source-package traceability

This patch adds read-only helpers for the third big-picture step: preparing the
local TIFF/RAG prototype for a real 5 TB server intake.

It does **not** OCR files, mutate the search database, or change graph artifacts.
It only audits the raw source package and writes planning reports.

## Files added

- `tiff/real_scale_intake.py`
- `scripts/audit_source_package_traceability.py`
- `scripts/plan_real_server_intake.py`
- `tests/unit/test_tiff_real_scale_intake.py`

## Source ZIP to organization traceability

Use this to prove that the raw public TIFF ZIP matches the current processed
organization export by normalized page number.

```bash
python scripts/audit_source_package_traceability.py \
  --zip /c/Users/juswil/Documents/00000027/metadata.zip \
  --write-json
```

Expected for the current sample:

```text
ZIP TIFF files: 509
Organization pages: 509
Matched pages by normalized number: 509
Status: OK
```

The warning that the ZIP has no `.txt` OCR files is expected. The ZIP is the raw
TIFF package. OCR lives in the processed working export.

## Real-server intake plan

Use this to generate a staged plan and rough scale estimate based on the sample
ZIP.

```bash
python scripts/plan_real_server_intake.py \
  --source-zip /c/Users/juswil/Documents/00000027/metadata.zip \
  --target-total-tb 5 \
  --write-json
```

This prints:

- current source ZIP shape
- ZIP to organization traceability
- rough page estimate for a 5 TiB archive using the sample TIFF size
- suggested baseline batch count
- first-pass stages
- production risks such as OCR not being included in the raw ZIP

## Intended production shape

```text
First pass:
  read-only inventory
  OCR import/generation plan
  batched baseline processing
  PostgreSQL graph/catalog writer
  OpenSearch writer
  Qdrant writer
  quality gate

After baseline:
  changed-file feed or metadata comparison
  process only new/changed/missing files
```

The raw TIFF bytes stay on the file server/ResCarta. PostgreSQL stores the
catalog/graph, OpenSearch stores searchable OCR text, and Qdrant stores vectors
with IDs back into the graph.
