# TIFF RAG eval expansion patch

This patch expands the normal backend RAG eval from the 4-question starter set to a larger local-only eval set.

The eval command is command-line-first:

```text
python scripts/evaluate_rag_questions.py
    -> prints progress and summary in the terminal
    -> writes CSV and JSON
    -> does not write HTML unless --write-html is used
```

## Files changed

```text
tiff/rag_eval_questions.py
tiff/rag_eval.py
scripts/evaluate_rag_questions.py
scripts/write_expanded_rag_eval_questions.py
tests/unit/test_tiff_rag_eval_expanded.py
README_tiff_rag_eval_expansion.md
```

## What the expanded eval checks

The expanded default set has 21 questions. It covers:

```text
exact part lookup
reverse nomenclature lookup
magazine holder structured summaries
source-page lookup
known real part references from QA
retrieval-only ATA evidence
retrieval-only passenger seat back evidence
one broad LLM answer marked for manual review
```

The default set intentionally keeps only one broad LLM/manual-review question so the normal pipeline quality gate should not be overwhelmed by manual-review rows.

## Apply and run

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026
unzip -o ~/Downloads/heico_tiff_rag_eval_expansion_patch.zip -d .
python -m pytest tests/unit/test_tiff_rag_eval_expanded.py -q
python scripts/write_expanded_rag_eval_questions.py --list
```

Then run a smoke eval first:

```bash
python scripts/evaluate_rag_questions.py --config local_config.yaml --questions local_data/evals/rag_eval_questions.json --limit 8
```

If that looks good, run the full normal eval:

```bash
python scripts/evaluate_rag_questions.py --config local_config.yaml --questions local_data/evals/rag_eval_questions.json
python scripts/check_pipeline_quality.py
python scripts/show_pipeline_status.py
```

## HTML

No HTML is written by default. The legacy HTML report is still available only when explicitly requested:

```bash
python scripts/evaluate_rag_questions.py --config local_config.yaml --questions local_data/evals/rag_eval_questions.json --write-html
```
