# TIFF RAG Model Evaluation

This patch adds a repeatable model-comparison layer for the local TIFF RAG system.

It compares local Ollama LLM answer models using the existing `scripts/ask_tiff_rag.py` command.
The script does not replace the existing RAG evaluation. It adds a broader model-comparison report.

## Files

```text
tiff/rag_model_eval.py
scripts/evaluate_rag_models.py
tests/unit/test_tiff_rag_model_eval.py
```

## Write the expanded question set

```bash
python scripts/evaluate_rag_models.py --write-default-questions --questions local_data/evals/rag_model_eval_questions.json
```

## Quick smoke test with Gemma only

```bash
python scripts/evaluate_rag_models.py --config local_config.yaml --models gemma3:12B --limit 3
```

## Compare Gemma and Llama

```bash
python scripts/evaluate_rag_models.py --config local_config.yaml --models gemma3:12B llama3.1:8b
```

Outputs:

```text
local_data/evals/model_compare/rag_model_eval_results.csv
local_data/evals/model_compare/rag_model_eval_results.json
local_data/evals/model_compare/rag_model_eval_results.html
```

## Why this matters

The backend now has:

```text
pipeline manifest
quality gate
structured source links
incremental embedding reuse
```

This model-eval layer helps decide which local LLM should be the default for broader summary questions while preserving deterministic answers for exact part lookups.
