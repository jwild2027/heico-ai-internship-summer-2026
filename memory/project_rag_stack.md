---
name: project-rag-stack
description: What this repo is — local-first RAG pipeline for technical PDFs (seaplane handbook is the test corpus). Names the active components so future sessions don't re-derive them.
metadata:
  type: project
---

This is a local-first RAG system for querying technical PDFs. Stack: Ollama (LLM + embeddings) + BGE embeddings + Chroma (vectors) + SQLite (source of truth for docs/pages/chunks).

**Active pipeline (the live thing):**
- Ingest: `rag_benchmark.py ingest` → calls [[db-ingest-bridge]] which wires PyMuPDF + OCR fallback ([tools/pymupdf_bge_chroma_cli.py](tools/pymupdf_bge_chroma_cli.py), [rag_benchmark.py](rag_benchmark.py)) → strategy selector ([tools/chunking_strategy.py](tools/chunking_strategy.py)) picks flat vs parent-child ([tools/parent_child_chunker.py](tools/parent_child_chunker.py)) → BGE embeddings → Chroma + SQLite.
- Query: [rag_chat.py](rag_chat.py) Streamlit UI → [tools/langchain_adapter.py](tools/langchain_adapter.py) does retrieval + HyDE + parent expansion + Ollama answer → [tools/citation_checker.py](tools/citation_checker.py) verifies claims against retrieved chunks, refuses if too few verify.

**Current branch focus (`rag-part2`):** parent-child chunking + SQLite as source of truth. Chroma is just an index keyed on chunk IDs that live in SQLite.

**Why:** internship deliverable demonstrating a working local RAG with measurable quality (benchmarks in `benchmarks/`) and answer grounding (citation_checker), not a black-box demo.

**How to apply:** When the user mentions "the pipeline," "ingest," "the chat," "retrieval," default to assuming the active pipeline above. The `streamlit_app.py` at the root is an unrelated Gemma word-graph experiment — don't confuse it with `rag_chat.py`. See [[project-repo-layout]] for what's experimental vs production.
