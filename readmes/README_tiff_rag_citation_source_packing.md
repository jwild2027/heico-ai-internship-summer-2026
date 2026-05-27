# TIFF RAG Citation-Safe Source Packing

This patch improves broad hybrid RAG answers after hybrid retrieval is enabled.

## Problem it fixes

Hybrid retrieval can return a flat source list that mixes:

- catalog/nomenclature sources,
- part-number mention pages,
- keyword OCR hits,
- vector/semantic hits.

For a question such as:

```text
Summarize the sources related to magazine holder parts.
```

Gemma may correctly identify the relevant part numbers, but can accidentally attach the wrong source citation to the wrong part number because all sources were presented as one flat list.

## What this patch adds

The answer layer now packs sources before sending them to the LLM:

1. catalog/nomenclature sources first,
2. mention-only pages grouped under the same part number,
3. a small amount of keyword/vector context at the end,
4. a structured evidence map in the prompt.

The evidence map tells the LLM exactly which source numbers belong to which part number.

## Expected behavior

For exact lookups, behavior is unchanged:

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model gemma3:12B "What is part number 120-37313-001?"
```

Expected:

```text
LLM used: False
Embeddings used: False
```

For broad hybrid summaries:

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model gemma3:12B --answer-mode summarize --retrieval-mode hybrid "Summarize the sources related to magazine holder parts." --top-k 8
```

Expected:

```text
LLM used: True
Embeddings used: True
```

The answer should keep citations attached to the correct part number more reliably.

## New test

```bash
python -m pytest tests/unit/test_tiff_rag_source_packing.py -q
```
