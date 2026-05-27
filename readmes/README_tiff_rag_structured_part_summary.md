# TIFF RAG Structured Part Summaries

This patch makes broad part/nomenclature summary answers citation-safe.

## Problem

Hybrid retrieval now collects the right sources from:

- cleaned part catalog rows,
- reverse nomenclature lookup,
- exact part-number mentions,
- keyword OCR search,
- vector search.

For questions such as:

```text
Summarize the sources related to magazine holder parts.
```

Gemma can still accidentally attach a mention page for one part number to a different part number. That is risky for technical manuals.

## What changed

The answer layer now builds structured part summaries in code when the retriever finds multiple catalog-backed part numbers.

The output groups evidence like this:

```text
1. 120-37313-001 - HOLDER, MAGAZINE
   Primary catalog source:
   - Page 1056

   Additional pages where 120-37313-001 appears:
   - Page 1059
   - Page 1065

2. 120-36843-001 - HOLDER, MAGAZINE
   Primary catalog source:
   - Page 1082

   Additional pages where 120-36843-001 appears:
   - Page 1079
   - Page 1086
```

Keyword and vector hits are placed under:

```text
Supplemental related pages from keyword/vector retrieval
```

They are no longer treated as proof of the part-number/nomenclature relationship.

## Expected behavior

Run:

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model gemma3:12B --answer-mode summarize --retrieval-mode hybrid "Summarize the sources related to magazine holder parts." --top-k 8
```

Expected flags:

```text
LLM used: False
Embeddings used: True
```

That is intentional. Hybrid retrieval can still use embeddings, but the final grouped part summary is generated deterministically to avoid citation mix-ups.

To force a Gemma-written answer for comparison:

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model gemma3:12B --answer-mode summarize --retrieval-mode hybrid --force-llm "Summarize the sources related to magazine holder parts." --top-k 8
```

## Install/test

```bash
python -m pytest tests/unit/test_tiff_rag_structured_part_summary.py tests/unit/test_tiff_rag_source_packing.py tests/unit/test_tiff_rag_hybrid_routing.py tests/unit/test_tiff_rag_answer.py -q
```
