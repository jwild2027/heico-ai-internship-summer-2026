# TIFF RAG reverse lookup balancing

This patch improves nomenclature/name searches such as:

```text
magazine holder
Where is magazine holder shown?
```

The previous reverse lookup correctly found matching catalog part numbers, but the global `top_k` source cap could let the first matching part number consume nearly all additional source slots. That meant later matching part numbers could show their catalog source but not their additional part-number mention pages.

## What changed

- `tiff/rag_retriever.py`
  - Adds balanced source grouping for nomenclature searches.
  - Treats `top_k` as a **per-part additional mention cap** for reverse lookups.
  - Keeps the matching catalog sources first.
  - Adds additional `part_mentions` pages under each matched part number.
  - Avoids adding duplicate part mention rows for the same page as the catalog source.

- `tiff/rag_answer.py`
  - Included for consistency with the nomenclature/source-grouped answer formatting.

- `tests/unit/test_tiff_rag_reverse_lookup_balanced_sources.py`
  - Verifies that a name search matching multiple part numbers returns mention pages for each matching part, not just the first one.

## Example

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model llama3.1:8b "Where is magazine holder shown?" --top-k 12
```

Expected behavior:

```text
I found these part numbers matching that nomenclature:
- 120-36843-001: HOLDER, MAGAZINE
- 120-37313-001: HOLDER, MAGAZINE
- 120-37313-535: HOLDER, MAGAZINE

Match 1: ...
Additional pages where 120-36843-001 appears:
...

Match 2: ...
Additional pages where 120-37313-001 appears:
...

Match 3: ...
Additional pages where 120-37313-535 appears:
...
```

For reverse lookup, use a higher `--top-k` when you want more mention pages per part number.
