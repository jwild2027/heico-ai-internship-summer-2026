# TIFF RAG ATA query fix

This patch adds a deterministic ATA-section answer path to `scripts/ask_tiff_rag.py`.

Why:

```text
python scripts/ask_tiff_rag.py --config local_config.yaml "Find evidence for ATA 25-21-00."
```

was falling through the generic RAG/part lookup path and could return:

```text
I did not find matching local TIFF/OCR sources for that question.
```

even though the logical organization export already knows ATA `25-21-00` has pages.

The fix reads the exported organization JSON files:

```text
local_data/organization/export/ata_tree.json
local_data/organization/export/page_index.json
```

and answers ATA-section browse/evidence requests directly, without LLM or embeddings.

Run:

```bash
python -m pytest tests/unit/test_tiff_rag_ata_answer.py -q
python scripts/ask_tiff_rag.py --config local_config.yaml "Find evidence for ATA 25-21-00."
```

Expected:

```text
LLM used: False
Embeddings used: False
ATA 25-21-00 is present in the local organization tree.
Sample source pages:
...
```
