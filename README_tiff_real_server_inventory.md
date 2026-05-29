# TIFF real-server inventory estimator

This patch adds a read-only inventory tool for a real TIFF server path or a source ZIP. It is meant to be run before OCR, indexing, Qdrant, OpenSearch, PostgreSQL migration, or graph generation on a large archive.

The tool does **not** open TIFF image bytes for OCR. It only lists files and reads file metadata such as path, extension, size, and directory structure.

## Files added

```text
tiff/real_server_inventory.py
scripts/audit_real_server_inventory.py
tests/unit/test_tiff_real_server_inventory.py
```

## Run tests

```bash
python -m pytest tests/unit/test_tiff_real_server_inventory.py -q
```

## Audit the current public/source ZIP

```bash
python scripts/audit_real_server_inventory.py \
  --zip /c/Users/juswil/Documents/00000027/metadata.zip \
  --target-total-tb 5 \
  --write-json
```

## Audit a future real server path

```bash
python scripts/audit_real_server_inventory.py \
  --root /path/to/tiff/server/root \
  --target-total-tb 5 \
  --write-json
```

For a fast sample inventory of a huge tree:

```bash
python scripts/audit_real_server_inventory.py \
  --root /path/to/tiff/server/root \
  --target-total-tb 5 \
  --max-files 100000 \
  --write-json
```

## Output

Default JSON output:

```text
local_data/batch_audit/real_server_inventory.json
```

The report includes:

```text
file counts
TIFF counts and bytes
OCR text counts and bytes
metadata counts
empty file count
extension counts
sample files
TIFF size stats
OCR/TIFF stem pairing
rough 5 TiB page estimate
batch estimate
storage estimate for OCR/OpenSearch/Qdrant/PostgreSQL catalog
processing-time estimate for OCR/page-context/embedding passes
```

## Why this matters

The 509-page sample has very small TIFFs, so extrapolating directly to 5 TiB can imply a very large page count. This audit lets us measure the real server before committing to OCR, OpenSearch, Qdrant, page-context LLM scans, or PostgreSQL migration.

Recommended production sequence:

```text
1. Read-only inventory
2. OCR coverage audit
3. Small pilot batch
4. Baseline batches
5. PostgreSQL/OpenSearch/Qdrant/graph writers
6. Quality gate after each batch
7. Incremental changed-file processing
```
