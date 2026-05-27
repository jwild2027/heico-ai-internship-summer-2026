# TIFF QA pipeline integration cleanup

This patch makes the QA severity cleanup part of the normal backend pipeline.

## What it fixes

Before this patch:

```text
python scripts/triage_part_catalog_qa.py --replace-all-report
```

updated the QA CSV/JSON report, but the latest pipeline manifest still showed
the old raw QA summary. That is why `check_pipeline_quality.py` and
`show_pipeline_status.py` still printed 205 QA review rows even after triage
showed 149.

After this patch:

```text
part_catalog_qa
    -> writes raw QA
part_catalog_qa_triage
    -> rewrites normal QA CSV/JSON with triaged severity
manifest
    -> summarizes the triaged QA report
quality gate
    -> reads the triaged manifest summary
```

## HTML behavior

The normal quality command no longer writes an HTML report. It prints the result
in the terminal and writes JSON only.

```bash
python scripts/check_pipeline_quality.py
```

To write the old HTML quality report manually:

```bash
python scripts/check_pipeline_quality.py --write-html
```

## Commands

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026
unzip -o ~/Downloads/heico_tiff_qa_pipeline_integration_patch.zip -d .
python -m pytest tests/unit/test_tiff_part_qa_severity.py tests/unit/test_tiff_pipeline_qa_integration.py -q
python scripts/triage_part_catalog_qa.py --replace-all-report && python scripts/check_pipeline_quality.py && python scripts/show_pipeline_status.py
```

## Future pipeline runs

Future full pipeline runs will include the QA triage step automatically:

```bash
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml
```

Expected step order includes:

```text
part_catalog_qa
part_catalog_qa_triage
rag_eval
```

To run raw QA without triage for debugging:

```bash
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml --skip-qa-triage
```
