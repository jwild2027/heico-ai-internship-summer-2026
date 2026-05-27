# TIFF RAG Evaluation + Part Catalog QA

This patch adds the next backend milestone after structured RAG answers:

- repeatable RAG question evaluation
- part-catalog QA reports
- local config file support
- a default `local_config.example.yaml`

The goal is to stop relying on one-off manual commands and start producing repeatable evidence that the system is improving.

## Files added

```text
tiff/local_config.py
tiff/rag_eval.py
tiff/part_qa.py

scripts/evaluate_rag_questions.py
scripts/report_part_catalog_qa.py
scripts/report_part_nomenclature_conflicts.py
scripts/report_nomenclature_groups.py
scripts/report_parts_missing_nomenclature.py
scripts/report_suspicious_part_ata.py

local_config.example.yaml

tests/unit/test_tiff_local_config.py
tests/unit/test_tiff_rag_eval.py
tests/unit/test_tiff_part_qa.py
```

`script/ask_tiff_rag.py` is also updated so it can read `--config local_config.yaml`.

## Config

Copy the example:

```bash
cp local_config.example.yaml local_config.yaml
```

Then edit if needed:

```yaml
db_path: local_data/db/tiff_search.db
embed_model: bge-m3:latest
llm_model: gemma3:12B
ollama_url: http://127.0.0.1:11434
top_k: 8
answer_mode: auto
retrieval_mode: hybrid
use_llm: true
use_embeddings: true
```

Now you can run:

```bash
python scripts/ask_tiff_rag.py --config local_config.yaml "Summarize the sources related to magazine holder parts."
```

instead of typing all model/database flags each time.

## RAG evaluation

Write a starter question set:

```bash
python scripts/evaluate_rag_questions.py --write-default-questions local_data/evals/rag_eval_questions.json
```

Run evaluation:

```bash
python scripts/evaluate_rag_questions.py --config local_config.yaml --questions local_data/evals/rag_eval_questions.json
```

Outputs:

```text
local_data/evals/rag_eval_results.csv
local_data/evals/rag_eval_results.json
local_data/evals/rag_eval_results.html
```

The report records:

```text
question
answer
status
LLM used
embeddings used
model names
elapsed time
source count
missing expected terms
missing expected sources
```

Statuses:

```text
pass          deterministic expected checks passed
fail          expected term/source was missing
manual_review LLM or broad-answer output needs human review
```

## Part catalog QA reports

Run all reports:

```bash
python scripts/report_part_catalog_qa.py --config local_config.yaml
```

Outputs:

```text
local_data/qa/part_catalog_qa_all.csv
local_data/qa/part_catalog_qa_all.json
local_data/qa/part_catalog_qa_all.html
```

Individual reports:

```bash
python scripts/report_part_nomenclature_conflicts.py --config local_config.yaml
python scripts/report_nomenclature_groups.py --config local_config.yaml
python scripts/report_parts_missing_nomenclature.py --config local_config.yaml
python scripts/report_suspicious_part_ata.py --config local_config.yaml
```

## What these reports mean

### Part nomenclature conflicts

Finds part numbers that had multiple raw nomenclature variants before cleanup.

Example:

```text
120-37313-001
  HOLDER, MAGAZINE
  HOLDER MAGAZINE
  HOLDER, MAGAZINE... VWS4956
```

Some are harmless OCR variants. Others may need review.

### Nomenclature groups

Finds part names that map to multiple part numbers.

Example:

```text
HOLDER, MAGAZINE
  120-37313-001
  120-36843-001
  120-37313-535
```

This is useful for reverse lookup and related-part discovery.

### Parts missing nomenclature

Finds detected part numbers that never got a clean name. These are candidates for OCR/table extraction improvements.

### Suspicious part ATA

Flags part mentions where the mention page ATA differs from the primary catalog ATA. These can be valid cross-references or extraction issues.

## Recommended next commands

```bash
python -m pytest tests/unit/test_tiff_local_config.py tests/unit/test_tiff_rag_eval.py tests/unit/test_tiff_part_qa.py -q
python scripts/evaluate_rag_questions.py --write-default-questions local_data/evals/rag_eval_questions.json
python scripts/evaluate_rag_questions.py --config local_config.yaml --questions local_data/evals/rag_eval_questions.json
python scripts/report_part_catalog_qa.py --config local_config.yaml
```
