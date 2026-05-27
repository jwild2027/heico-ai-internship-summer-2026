# TIFF part QA severity cleanup

This patch keeps the QA review command-line-first and tightens the remaining severity categories.

It does not generate HTML. The terminal output is the main review surface.

## What changed in this pass

The previous pass still had many rows labeled `unclassified_review`. This pass adds clearer categories:

```text
real_part_catalog_review
    A plausible part number still needs human review, but the raw QA row did not say whether it was a conflict, missing nomenclature, etc.

non_part_figure_or_sheet_reference
    Values like 00-08A, 00-30A, etc. are treated as figure/sheet/item references, not part catalog problems.

non_part_slash_reference
    Values like E0/5221 are slash codes that do not look like part groups.

compound_part_reference
    Values like 120-29067-019/029 are slash-separated part groups/ranges. They are useful evidence, but they are not one canonical part row to manually review.
```

## Run from Git Bash

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026
unzip -o ~/Downloads/heico_tiff_part_qa_severity_v2_patch.zip -d .
python -m pytest tests/unit/test_tiff_part_qa_severity.py -q
python scripts/triage_part_catalog_qa.py --show all --limit 60
```

## Useful review commands

```bash
python scripts/triage_part_catalog_qa.py --show review --limit 60
python scripts/triage_part_catalog_qa.py --show suppressed --limit 60
python scripts/triage_part_catalog_qa.py --show all --limit 400 | grep "category=unclassified_review"
python scripts/triage_part_catalog_qa.py --show all --limit 400 | grep "category=real_part_catalog_review" | head -40
```

The `unclassified_review` grep should ideally print nothing, or close to nothing. Real part rows should now be labeled `real_part_catalog_review`, `real_part_nomenclature_conflict`, or `real_part_missing_nomenclature`.

## Optional: write CSV/JSON audit files

```bash
python scripts/triage_part_catalog_qa.py --write-files
```

This writes:

```text
local_data/qa/part_catalog_qa_triaged.csv
local_data/qa/part_catalog_qa_triaged.json
```

It does not write HTML.

## Optional: replace the normal QA report after reviewing terminal output

```bash
python scripts/triage_part_catalog_qa.py --replace-all-report
python scripts/check_pipeline_quality.py
```

When `--replace-all-report` is used, the old raw CSV/JSON files are backed up first as `.raw.bak`.
