# TIFF QA no-HTML default patch

This patch makes the raw part-catalog QA command command-line first.

## Behavior

```text
python scripts/report_part_catalog_qa.py
    -> prints summary in the terminal
    -> writes CSV
    -> writes JSON
    -> does not write HTML by default
```

HTML is still available only when explicitly requested:

```bash
python scripts/report_part_catalog_qa.py --config local_config.yaml --write-html
```

## Files

```text
scripts/report_part_catalog_qa.py
tests/unit/test_report_part_catalog_qa_cli.py
README_tiff_qa_no_html.md
```
