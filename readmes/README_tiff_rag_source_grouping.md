# TIFF RAG source grouping patch

This patch improves exact part-number answers in the local TIFF RAG layer.

## What changed

Before this patch, a question such as:

```text
What is part number 120-37313-001?
```

could return the correct cleaned nomenclature, but the LLM could also phrase the answer as if every matching page proved the nomenclature.

After this patch, exact part-number answers are deterministic when the cleaned/catalog source has the nomenclature:

```text
120-37313-001 is listed as HOLDER, MAGAZINE.

Primary nomenclature source:
1. T.P. 120/1176 - ATA 25-21-00 - Page 1056
   TIFF: ...
   OCR: ...

Additional pages where this part number appears:
- T.P. 120/1176 - ATA ... - Page ...
```

## Design

The retriever still collects evidence in this order:

1. `part_catalog_clean`
2. `part_catalog`
3. `part_mentions`
4. keyword OCR chunks
5. vector chunks

The answer layer now separates:

- primary nomenclature sources, which prove the part name
- additional mention pages, which only show where the part number appears

For exact part-number questions with a catalog nomenclature, the system answers from code instead of asking the LLM to decide the part name. This keeps the core fact source-backed and avoids OCR-noise repetition.

## Files patched

```text
tiff/rag_answer.py
tiff/rag_retriever.py
tiff/rag_web_ui.py
tests/unit/test_tiff_rag_source_grouping.py
```

## Run

```bash
python -m pytest tests/unit/test_tiff_rag_source_grouping.py tests/unit/test_tiff_rag_answer.py tests/unit/test_tiff_rag_retriever.py -q
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model llama3.1:8b "What is part number 120-37313-001?"
```

Expected behavior:

```text
LLM used: False
120-37313-001 is listed as HOLDER, MAGAZINE.
Primary nomenclature source:
Additional pages where this part number appears:
```

The `LLM used: False` value is expected for exact part-number questions. The cleaned catalog is more reliable than asking the LLM to infer a part name.
