# TIFF page-context JSON parse/Ollama API fix

This patch improves `generate_page_contexts.py` for real Gemma/Ollama page-context scans.

It fixes two issues:

1. Prefer Ollama's local HTTP API with `format: "json"` instead of parsing CLI output.
2. Parse otherwise valid model JSON that contains literal control characters/newlines inside strings.

The graph/context model is unchanged:

```text
Page --HAS_CONTEXT--> PageContext
PageContext --SUMMARIZES--> Page
PageContext --TAGGED_AS--> Topic
PageContext --HIGHLIGHTS_PART--> Part
```

Recommended test:

```bash
python -m pytest tests/unit/test_tiff_page_context_graph.py -q
python scripts/generate_page_contexts.py --model gemma3:12B --limit 25 --force --write-json --show-error-details
python scripts/export_document_organization_graph.py --strict
```
