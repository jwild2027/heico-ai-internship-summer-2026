# TRACE-Net Active Project Map

## Active runtime direction

Open WebUI -> TRACE-Net bridge -> query planner -> read-only tools -> context pack -> Gemma4 -> Self-RAG critic -> CRAG repair -> final cited answer.

Gemma is not the database. TRACE-Net builds the evidence binder. Gemma drafts from it.

## Active proof lanes

- OCR/source text
- table evidence
- exact part lookup
- visual/image route summaries as guidance only
- graph/Postgres relationships as retrieval and source resolution
- Qdrant semantic recall as retrieval guidance
- Engram behavior memory as guidance only

## Active safety rules

- No source-truth mutation.
- No answer permission unless explicitly authorized.
- No Postgres/Qdrant/OpenSearch writes unless explicitly live-write gated.
- Engram, summaries, graph hits, vector hits, and feedback are not proof.
- Only current proof_context citations prove manual/source claims.

## Archive policy

Archived folders are kept for history but should not be treated as active runtime code.
Old patch folders, one-time apply scripts, debug outputs, legacy Chroma files, and generated run outputs should live under archive folders.
