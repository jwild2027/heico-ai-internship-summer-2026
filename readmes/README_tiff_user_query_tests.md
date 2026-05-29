# TIFF user-query test suite

This patch adds a black-box, user-style smoke suite for the current TIFF/RAG MVP.
It runs the same command-line paths a demo user or UI/API layer would exercise:

- organization export part lookup
- organization export ATA browse
- organization export page/source lookup
- graph traversal from part to page/context/source
- page context inspection
- deterministic RAG part lookup
- deterministic ATA lookup
- reverse nomenclature lookup
- optional slow LLM/RAG summary

It also adds a small read-only ZIP audit helper for public ResCarta-style TIFF ZIP
packages. The ZIP audit does not extract or OCR files; it only counts entries and
checks whether `metadata.xml` and TIFFs are present.

## Commands

```bash
python -m pytest tests/unit/test_tiff_user_query_tests.py tests/unit/test_tiff_public_tiff_zip_audit.py -q
python scripts/run_user_query_tests.py --config local_config.yaml --write-json
```

Optional slow LLM case:

```bash
python scripts/run_user_query_tests.py --config local_config.yaml --include-slow --write-json
```

List cases:

```bash
python scripts/run_user_query_tests.py --list
```

Run one case:

```bash
python scripts/run_user_query_tests.py --case rag_exact_part_120_37313_001 --write-json
```

Audit the uploaded public TIFF ZIP:

```bash
python scripts/audit_public_tiff_zip.py --zip ~/Downloads/metadata.zip --write-json
```

Expected for the attached public ZIP shape is roughly:

```text
metadata.xml present: True
TIFF files: 509
OCR text files: 0
```

No OCR text in the ZIP is not automatically a failure. It just means OCR must come
from another export/source or be generated before the full backend can index the
package.
