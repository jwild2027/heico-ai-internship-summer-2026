# Page visual/object audit

This read-only audit counts page-level visual, figure, sheet, table, and illustration signals from:

- organization `page_index.json`
- OCR text paths
- AI page-context roles/topics/summaries
- graph summary counts, when available

It does not perform image-region detection yet. It is an OCR/context-based object-signal audit.

## Run

```bash
python scripts/audit_page_visual_objects.py --write-json
```

Optional strict mode:

```bash
python scripts/audit_page_visual_objects.py --strict --write-json
```

Output:

```text
local_data/organization/page_visual_objects_audit.json
```

## What it reports

- page role counts: `figure`, `table`, `parts_list`, `procedure`, `blank`, etc.
- pages with figure references
- pages with sheet references
- pages with table references
- pages with illustration/image/diagram terms
- likely visual pages
- likely table pages
- likely figure pages
- source/context/OCR coverage
- sample rows for review

## Future extension

A later image-analysis pass can add true object detection from TIFFs:

- table region detection
- figure/image region detection
- diagram/schematic detection
- blank-page visual verification
- bounding boxes

For now, this audit is intentionally cheap and text-first.
