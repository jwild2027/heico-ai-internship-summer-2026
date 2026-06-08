# TRACE-Net source citation import fix

Fixes direct script execution for:

- `scripts/build_trace_net_source_citations.py`
- `scripts/check_trace_net_source_citation_quality.py`

When Python runs `python scripts/<script>.py`, it places `scripts/` on `sys.path`, not the repository root. These wrappers now insert the repo root before importing `tiff.*` modules.

Run:

```bash
python scripts/build_trace_net_source_citations.py --open
python scripts/check_trace_net_source_citation_quality.py \
  --write-json \
  --min-citations 1426 \
  --min-pages 509 \
  --min-source-traceable 1426 \
  --max-unsafe-citations 0 \
  --max-missing-source-url 0
```
