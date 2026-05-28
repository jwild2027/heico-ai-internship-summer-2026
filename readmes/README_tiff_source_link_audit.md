# TIFF source-link audit patch

This patch adds a command-line audit for the source-link layer.

It answers one question:

```text
Can RAG/search results reliably point back to TIFF, OCR, and ResCarta/source pages?
```

No HTML is written.

## Added files

```text
tiff/source_link_audit.py
scripts/audit_source_links.py
tests/unit/test_tiff_source_link_audit.py
README_tiff_source_link_audit.md
```

## Commands

```bash
python -m pytest tests/unit/test_tiff_source_link_audit.py -q
python scripts/audit_source_links.py --config local_config.yaml
```

Useful variants:

```bash
python scripts/audit_source_links.py --config local_config.yaml --sample-part 120-37313-001 --sample-part AM03078-22
python scripts/audit_source_links.py --config local_config.yaml --write-json
python scripts/audit_source_links.py --config local_config.yaml --strict
```

Later, after the real ResCarta URL template is known:

```bash
python scripts/audit_source_links.py --config local_config.yaml --require-real-rescarta
```

## What to expect now

With the current placeholder template, this is expected:

```text
Local/placeholder ResCarta URLs: 509
Real ResCarta deep-link ready: no
```

That is not a failure yet. It means source links exist and are usable locally, but the final ResCarta deep-link format still needs to be swapped in when known.

The important current checks are:

```text
Total links should match indexed pages.
Pages without source links should be 0.
Missing TIFF paths should be 0.
Missing OCR paths should be 0.
Sample parts should resolve to source rows.
```
