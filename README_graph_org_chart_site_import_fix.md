# Graph org-chart site direct script import fix

This patch fixes direct execution of:

```bash
python scripts/build_graph_org_chart_site.py --expect-pages 509 --expect-documents 1
```

The previous script could fail with:

```text
ModuleNotFoundError: No module named 'tiff'
```

because Python sets `sys.path[0]` to `scripts/` when a script is executed by filename. The fixed script inserts the repository root into `sys.path` before importing `tiff.graph_org_chart_site`.

## Run

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026
unzip -o ~/Downloads/heico_graph_org_chart_site_import_fix.zip -d .
python -m pytest tests/unit/test_tiff_graph_org_chart_script_direct_run.py tests/unit/test_tiff_graph_org_chart_site.py tests/unit/test_tiff_current_graph_org_chart_site.py -q -s
python scripts/build_graph_org_chart_site.py --expect-pages 509 --expect-documents 1 --open
```

Or serve it:

```bash
python scripts/serve_graph_org_chart_site.py
```

Open:

```text
http://127.0.0.1:8765/index.html
```
