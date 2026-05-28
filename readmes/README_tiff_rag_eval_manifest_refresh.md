# TIFF RAG eval manifest refresh patch

This patch fixes the mismatch where a standalone expanded RAG eval shows 21 questions, but `show_pipeline_status.py` still shows the older 4-question eval summary.

## What it changes

```text
python scripts/evaluate_rag_questions.py
    -> writes CSV/JSON eval results
    -> for full normal eval runs, refreshes latest_backend_pipeline.json
    -> does not refresh the manifest for --limit smoke tests
```

The normal backend pipeline still writes the manifest at the end of the full run, so the pipeline step passes `--no-refresh-manifest` to avoid updating an old manifest in the middle of a run.

## Files changed

```text
tiff/pipeline_manifest.py
tiff/pipeline_runner.py
scripts/evaluate_rag_questions.py
tests/unit/test_tiff_rag_eval_manifest_refresh.py
README_tiff_rag_eval_manifest_refresh.md
```

## Commands

```bash
cd /c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026
unzip -o ~/Downloads/heico_tiff_rag_eval_manifest_refresh_patch.zip -d .
python -m pytest tests/unit/test_tiff_rag_eval_manifest_refresh.py tests/unit/test_tiff_rag_eval_expanded.py tests/unit/test_tiff_pipeline_qa_integration.py -q
python scripts/evaluate_rag_questions.py --config local_config.yaml --questions local_data/evals/rag_eval_questions.json && python scripts/check_pipeline_quality.py && python scripts/show_pipeline_status.py
```

Expected status output after the full eval:

```text
Eval summary:
  Questions: 21
  Status counts: {'manual_review': 1, 'pass': 20}
```
