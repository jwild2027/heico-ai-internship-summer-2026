# Graph org-chart browser render fix

This patch fixes a JavaScript escaping bug in `tiff/graph_org_chart_site.py`.

The previous generated `index.html` could contain an invalid browser regex inside
`escAttr()`, which caused the chart canvas to stay blank with an error like:

```text
Uncaught SyntaxError: Invalid regular expression: /\/g ...
```

The fix removes the fragile regex from `escAttr()` and uses `String.fromCharCode(92)`
plus `split().join()` escaping instead. This is safe for page/document IDs that
contain quotes, backslashes, or newlines.

## Rebuild and view

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026
unzip -o ~/Downloads/heico_graph_org_chart_site_browser_fix.zip -d .
python -m pytest tests/unit/test_tiff_graph_org_chart_site.py tests/unit/test_tiff_current_graph_org_chart_site.py tests/unit/test_tiff_graph_org_chart_script_direct_run.py tests/unit/test_tiff_graph_org_chart_browser_syntax.py -q -s
python scripts/build_graph_org_chart_site.py --expect-pages 509 --expect-documents 1
python scripts/serve_graph_org_chart_site.py
```

Then visit:

```text
http://127.0.0.1:8765/index.html
```

Serving from localhost is recommended over opening the HTML as `file:///...`,
because browsers apply stricter rules to local file URLs.
