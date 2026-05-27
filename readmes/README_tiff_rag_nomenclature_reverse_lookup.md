# TIFF RAG nomenclature reverse lookup

This patch adds the reverse of exact part-number lookup.

Before:

```text
120-37313-001 -> HOLDER, MAGAZINE + source pages
```

After:

```text
magazine holder -> 120-37313-001 + source pages where that part number appears
```

## What changed

- `tiff/rag_retriever.py`
  - Adds natural-language nomenclature token matching.
  - Matches user wording such as `magazine holder` against cleaned catalog names such as `HOLDER, MAGAZINE`.
  - Expands the resolved catalog part number into `part_mentions`, so the answer shows the pages where that part appears.

- `tiff/rag_answer.py`
  - Adds a deterministic answer path for nomenclature/name searches.
  - Separates the matching catalog source from additional part-number mention pages.
  - Avoids needing the LLM when the cleaned catalog can answer the lookup directly.

- `tiff/rag_web_ui.py`
  - Adds a UI source group for matching nomenclature sources.

- `tests/unit/test_tiff_rag_nomenclature_reverse_lookup.py`
  - Verifies that `magazine holder` resolves to `120-37313-001` and returns additional pages where that part number appears.

## Example commands

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model llama3.1:8b "magazine holder"
```

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model llama3.1:8b "Where is magazine holder shown?" --top-k 12
```

Expected behavior for exact cleaned catalog hits:

```text
LLM used: False
Embeddings used: False

HOLDER, MAGAZINE matches part number 120-37313-001.

Matching catalog source:
...

Additional pages where 120-37313-001 appears:
...
```

That is intentional. The local cleaned catalog already provides the source-backed answer, so the LLM does not need to guess.
