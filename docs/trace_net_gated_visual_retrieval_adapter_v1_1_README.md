# TRACE-Net Gated Visual Retrieval Adapter v1.1

This patch fixes the v1 retrieval adapter summary extraction.

## Why v1.1

The v1 adapter built 104 search-ready documents, 91 pages with part numbers, and
103 pages with figure references, but only recognized 7 pages as having a
summary. That was a schema-extraction issue, not a retrieval-pack failure.

v1.1 now:

- searches broader visual context fields
- mines useful visual text from `source_records`
- creates a deterministic, non-LLM evidence fallback summary from:
  - page id
  - detector route/subtype
  - figure refs
  - part-number candidates
  - callouts/items
  - nomenclature/descriptions

Fallback summaries are explicitly marked as:

```text
visual_summary_source = deterministic_evidence_fallback
```

They are retrieval guidance only, not proof or final answers.

## Safety

- no Ollama calls
- no LLM calls
- no OCR execution
- no database/vector/search writes
- no source-truth mutation
- no answer permission
