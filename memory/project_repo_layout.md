---
name: project-repo-layout
description: Which directories are the live RAG pipeline vs. experiments/scaffolding. Use this to scope changes — don't touch experimental code when fixing the main pipeline.
metadata:
  type: project
---

**Active pipeline (touch when fixing RAG):**
- `db/` — SQLite layer: schema, storage, ingest_bridge. Source of truth.
- `tools/pymupdf_bge_chroma_cli.py`, `tools/chunking_strategy.py`, `tools/parent_child_chunker.py`, `tools/chroma_client.py` — ingest pipeline.
- `tools/langchain_adapter.py`, `tools/citation_checker.py` — query + grounding.
- `rag_benchmark.py` — ingest/query/benchmark/status CLI (the main entry point).
- `rag_chat.py` — the Streamlit chat UI wired to the pipeline.

**Experiments and supporting work (usually don't touch when fixing main pipeline):**
- `benchmarks/` — embedding + latency benchmarks (3 variants of progressive difficulty).
- `pdf_scrapers/` — pluggable scraper comparison (pypdf, pdfplumber, pymupdf, unstructured).
- `model_pdf_ingestion/` — per-model wrappers around `backend/doc_ingest.py`.
- `backend/` — early scaffolding (Ollama prompt batching, vision experiments, Chroma hello-world).
- `copali/` — ColPali (visual doc embeddings) exploration, not wired into main pipeline.
- `tess-orc/ocr_util.py` — standalone Tesseract wrapper, not wired into main pipeline.

**Misleading filenames to know about:**
- `test.py` at root — vendored Ollama Pydantic models, NOT a test file.
- `streamlit_app.py` at root — Gemma word-graph experiment, NOT the RAG chat. The RAG chat is `rag_chat.py`.
- `pymupdf_bge_chroma_cli_copy.py` at root — thin launcher that imports the real CLI from `tools/`, NOT a backup copy.

**Debug output dirs that grow without cleanup:**
- `chunk_debug/` — overwritten by index each ingest but old trailing files persist.
- `ocr_debug/` — page renders + per-page text dumps.

**Why:** When asked to fix a bug in "the ingest" or "the chat," default to the active pipeline files. When asked about model comparison or scraper choice, look at the experiment dirs.

**How to apply:** If a change spans both groups, flag it — usually the user wants to keep experiments isolated.
