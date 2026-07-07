# TRACE-Net V2 Gemma summary sample runner v1

This is the real small laptop sample path for V2 summaries.

The earlier simple sample runner proved the scaffold/safety path, but it did not call Gemma.
This runner calls the existing V2 prompt builder and local Ollama/Gemma4.

Default model:

```text
gemma4:26b
```

Default Ollama endpoint:

```text
http://127.0.0.1:11434/api/generate
```

## Safety

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- V2 summaries are retrieval/query guidance only

## Why this is separate from V3

V2 remains the existing summary/query-guidance layer.
V3 should be a new richer page-intelligence layer that can include Engram behavior guidance, Leiden/community guidance, Dublin Core metadata, route signals, uncertainty fields, and extraction warnings.

This runner attaches a small `v3_preview` field, but only as report-only guidance.
