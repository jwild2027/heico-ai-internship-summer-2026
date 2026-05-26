#!/usr/bin/env python3
"""Streamlit RAG chat interface for querying ingested PDF documents.

Wired to the existing PyMuPDF + BGE + ChromaDB + Ollama pipeline.

Run:
    streamlit run rag_chat.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from src.rag.langchain_adapter import ask, DEFAULT_LLM_MODEL, DEFAULT_EMBED_MODEL
    from src.rag.langchain_adapter import DEFAULT_COLLECTION, DEFAULT_PERSIST_DIR
    from src.rag.langchain_adapter import DEFAULT_TOP_K, DEFAULT_FETCH_K, DEFAULT_USE_HYDE
    from src.rag.citation_checker import check_answer, format_checked_answer
    import tools.pymupdf_bge_chroma_cli as base
    PIPELINE_AVAILABLE = True
except Exception as e:
    PIPELINE_AVAILABLE = False
    PIPELINE_ERROR = str(e)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="RAG Document Chat",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}

/* Background */
.stApp {
    background-color: #0f1117;
    color: #e2e8f0;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #161b27;
    border-right: 1px solid #2d3748;
}

/* Chat messages */
.user-bubble {
    background: #1e3a5f;
    border: 1px solid #2b4c7e;
    border-radius: 12px 12px 2px 12px;
    padding: 12px 16px;
    margin: 8px 0;
    margin-left: 15%;
    color: #e2e8f0;
    font-size: 0.95rem;
    line-height: 1.6;
}

.assistant-bubble {
    background: #1a1f2e;
    border: 1px solid #2d3748;
    border-radius: 12px 12px 12px 2px;
    padding: 14px 18px;
    margin: 8px 0;
    margin-right: 10%;
    color: #e2e8f0;
    font-size: 0.95rem;
    line-height: 1.7;
}

.citation-bar {
    background: #0d1b2a;
    border: 1px solid #1e3a5f;
    border-radius: 6px;
    padding: 8px 12px;
    margin-top: 8px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: #64b5f6;
}

.citation-tag {
    display: inline-block;
    background: #1e3a5f;
    border: 1px solid #2b4c7e;
    border-radius: 4px;
    padding: 2px 8px;
    margin: 2px 3px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: #90caf9;
}

.meta-line {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #4a5568;
    margin-top: 6px;
}

.status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 6px;
}
.dot-green  { background: #48bb78; }
.dot-yellow { background: #ecc94b; }
.dot-red    { background: #f56565; }

/* Input styling */
.stTextInput > div > div > input {
    background-color: #1a1f2e !important;
    border: 1px solid #2d3748 !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
}

/* Button */
.stButton > button {
    background: #1e3a5f;
    border: 1px solid #2b4c7e;
    color: #90caf9;
    border-radius: 8px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    padding: 6px 16px;
    transition: all 0.15s;
}
.stButton > button:hover {
    background: #2b4c7e;
    border-color: #4a90d9;
    color: #e2e8f0;
}

/* Metrics */
[data-testid="metric-container"] {
    background: #161b27;
    border: 1px solid #2d3748;
    border-radius: 8px;
    padding: 10px 14px;
}

/* Expander */
.streamlit-expanderHeader {
    background: #161b27 !important;
    border: 1px solid #2d3748 !important;
    border-radius: 6px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.8rem !important;
    color: #4a90d9 !important;
}

/* Selectbox */
.stSelectbox > div > div {
    background-color: #1a1f2e !important;
    border-color: #2d3748 !important;
    color: #e2e8f0 !important;
}

/* Divider */
hr { border-color: #2d3748; }

/* Header */
h1, h2, h3 {
    font-family: 'IBM Plex Mono', monospace;
    color: #e2e8f0;
    letter-spacing: -0.5px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    st.markdown("---")
    st.markdown("### 🤖 AI Models")

    # Categorized model catalog — what each model can handle
    LLM_MODELS = {
        "gemma3:4b":      {"label": "gemma3:4b",       "tags": "📝 Text · ⚡ Fast",                "size": "3.3 GB"},
        "gemma3:12B":     {"label": "gemma3:12B",      "tags": "📝 Text · 🎯 Better quality",      "size": "8.1 GB"},
        "llama3.1:8b":    {"label": "llama3.1:8b",     "tags": "📝 Text · ⚖️ Balanced",            "size": "4.9 GB"},
        "llama3.2:1b":    {"label": "llama3.2:1b",     "tags": "📝 Text · 🚀 Very fast, lower quality", "size": "1.3 GB"},
        "phi3:mini":      {"label": "phi3:mini",       "tags": "📝 Text · 🧠 Reasoning",            "size": "2.2 GB"},
        "qwen3-vl":       {"label": "qwen3-vl",        "tags": "📝 Text · 🖼️ Images · Vision",     "size": "6.1 GB"},
        "llava:13b":      {"label": "llava:13b",       "tags": "📝 Text · 🖼️ Images · Vision",     "size": "8.0 GB"},
    }

    EMBED_MODELS = {
        "bge-large":         {"label": "bge-large",         "tags": "🔍 Text search · 🎯 High accuracy",        "size": "670 MB"},
        "bge-m3":            {"label": "bge-m3",            "tags": "🔍 Text search · 🌍 Multilingual",          "size": "1.2 GB"},
        "mxbai-embed-large": {"label": "mxbai-embed-large", "tags": "🔍 Text search · ⚖️ Balanced",              "size": "669 MB"},
        "nomic-embed-text":  {"label": "nomic-embed-text",  "tags": "🔍 Text search · 🚀 Fast, smaller",         "size": "274 MB"},
    }

    def _format_llm(name: str) -> str:
        info = LLM_MODELS.get(name, {"tags": "", "size": ""})
        return f"{name}  —  {info['tags']}"

    def _format_embed(name: str) -> str:
        info = EMBED_MODELS.get(name, {"tags": "", "size": ""})
        return f"{name}  —  {info['tags']}"

    llm_model = st.selectbox(
        "Answer model",
        list(LLM_MODELS.keys()),
        index=0,
        format_func=_format_llm,
        help=(
            "The AI model that reads retrieved passages and writes the answer.\n\n"
            "📝 Text-only models are best for document Q&A.\n"
            "🖼️ Vision models (qwen3-vl, llava) can also describe images.\n"
            "⚡ Smaller = faster, larger = more thorough.\n\n"
            "Recommended: gemma3:4b for daily use, gemma3:12B for tough questions."
        ),
    )
    st.caption(f"💾 {LLM_MODELS[llm_model]['size']}  ·  {LLM_MODELS[llm_model]['tags']}")

    embed_model = st.selectbox(
        "Search model",
        list(EMBED_MODELS.keys()),
        index=0,
        format_func=_format_embed,
        help=(
            "Used to understand your question and find relevant passages.\n\n"
            "⚠️ Must match the model used when documents were ingested. "
            "If you change this, you need to re-ingest your PDFs."
        ),
    )
    st.caption(f"💾 {EMBED_MODELS[embed_model]['size']}  ·  {EMBED_MODELS[embed_model]['tags']}")

    st.markdown("---")
    st.markdown("### 🎛️ Search Settings")

    top_k = st.slider(
        "Number of sources to use",
        min_value=3,
        max_value=10,
        value=6,
        help=(
            "How many document passages the AI reads before writing its answer. "
            "Higher = more context, slower response. "
            "Lower = faster but may miss relevant info. "
            "6 is a good default for most questions."
        ),
    )
    st.caption(f"📖 AI will read **{top_k} passages** to compose its answer")

    fetch_k = st.slider(
        "Search pool size",
        min_value=10,
        max_value=30,
        value=20,
        help=(
            "How many candidate passages are pulled from the database before the best ones are selected. "
            "Think of it as a shortlist size — the AI pulls this many candidates, "
            "then picks the top ones to actually read. "
            "Larger pool = better chance of finding the right passage. "
            "Recommended: always keep this higher than 'Number of sources to use'."
        ),
    )
    st.caption(f"🔍 Searching through **{fetch_k} candidates**, keeping the best {top_k}")

    st.markdown("---")
    st.markdown("### 🔍 Answer Verification")

    verify_claims = st.toggle(
        "Check answer against sources",
        value=True,
        help=(
            "When enabled, every sentence in the AI's answer is automatically checked "
            "against the retrieved document passages. "
            "If a claim can't be traced back to a source, it gets flagged as [UNVERIFIED]. "
            "If too many claims are unverifiable, the answer is refused entirely to prevent misinformation. "
            "Recommended: keep this on."
        ),
    )

    refusal_threshold = st.slider(
        "Strictness level",
        min_value=0.0,
        max_value=1.0,
        value=0.40,
        step=0.05,
        help=(
            "Controls how strict the verification is. "
            "0% = accept any answer even if nothing is verified. "
            "40% = refuse if fewer than 40% of claims have sources (recommended). "
            "100% = every single claim must be verified or the answer is refused. "
            "For sensitive or compliance use cases, set this higher (60-80%)."
        ),
    )
    pct = int(refusal_threshold * 100)
    st.caption(f"⚖️ Answers refused if less than **{pct}%** of claims are verified")

    st.markdown("---")
    st.markdown("### 🔭 Retrieval Enhancement")

    use_hyde = st.toggle(
        "Smart query expansion (HyDE)",
        value=False,
        help=(
            "HyDE (Hypothetical Document Embeddings) generates a fake answer first, "
            "then uses it to search. Helps when your question uses different words "
            "than the document.\n\n"
            "⚠️ Can hurt accuracy on small, well-structured documents. "
            "Best for large messy corpora where direct keyword match struggles. "
            "Try it on/off and see what works better for your documents."
        ),
    )
    if use_hyde:
        st.caption("🧠 Generating hypothetical answer to improve search")
    else:
        st.caption("⚡ Searching directly with your query (faster, often more accurate)")

    st.markdown("---")
    st.markdown("### 📊 DB Status")

    if PIPELINE_AVAILABLE:
        try:
            collection = base.get_collection(DEFAULT_PERSIST_DIR, DEFAULT_COLLECTION)
            count = collection.count()
            if count > 0:
                st.markdown(f'<span class="status-dot dot-green"></span>**{count}** chunks indexed', unsafe_allow_html=True)
            else:
                st.markdown('<span class="status-dot dot-yellow"></span>No chunks — run ingest first', unsafe_allow_html=True)
        except Exception:
            st.markdown('<span class="status-dot dot-red"></span>ChromaDB unavailable', unsafe_allow_html=True)
    else:
        st.markdown(f'<span class="status-dot dot-red"></span>Pipeline error', unsafe_allow_html=True)
        st.caption(PIPELINE_ERROR if 'PIPELINE_ERROR' in dir() else "Unknown error")

    st.markdown("---")
    st.markdown("### 💡 Example queries")
    example_queries = [
        "What are sponsons?",
        "What is the step on a float?",
        "What causes weathervaning?",
        "What makes glassy water dangerous?",
        "How do buoys mark channels?",
        "What regulations apply on water?",
    ]
    for q in example_queries:
        if st.button(q, key=f"ex_{q}"):
            st.session_state.pending_query = q

    st.markdown("---")
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.markdown("# 📄 RAG Document Chat")
st.markdown("Ask questions about your ingested PDF documents. Answers are grounded in retrieved context.")
st.markdown("---")

# Init session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render chat history
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f'<div class="user-bubble">🧑 {msg["content"]}</div>', unsafe_allow_html=True)
    else:
        answer   = msg["content"]
        citations = msg.get("citations", [])
        latency  = msg.get("latency_ms", 0)
        grounded = msg.get("grounded", True)

        dot = "dot-green" if grounded else "dot-yellow"
        label = "grounded" if grounded else "not grounded"

        # Verification stats if available
        checked = msg.get("checked")
        verify_info = ""
        if checked:
            rate = f"{checked.verification_rate:.0%}"
            v_color = "dot-green" if checked.verified else "dot-red"
            verify_info = (
                f' · <span class="status-dot {v_color}"></span>'
                f'{checked.verified_count}/{checked.claim_count} claims verified ({rate})'
            )

        citation_html = ""
        if citations:
            tags = ""
            for c in citations:
                page = (
                    f"p{c['page_start']}"
                    if c["page_start"] == c["page_end"]
                    else f"p{c['page_start']}–p{c['page_end']}"
                )
                title = c.get("title", "")
                tip = f"{page}" + (f" · {title[:40]}" if title else "")
                tags += f'<span class="citation-tag">{tip}</span>'
            citation_html = f'<div class="citation-bar">📎 Sources: {tags}</div>'

        hyde_info = ""
        if msg.get("hyde_used"):
            hyde_info = ' · <span style="color:#9f7aea">🔭 HyDE</span>'

        st.markdown(
            f'<div class="assistant-bubble">'
            f'🤖 {answer}'
            f'{citation_html}'
            f'<div class="meta-line">'
            f'<span class="status-dot {dot}"></span>{label} · {latency}ms · {llm_model}'
            f'{verify_info}{hyde_info}'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

col_input, col_btn = st.columns([5, 1])

with col_input:
    pending = st.session_state.pop("pending_query", "")
    query = st.text_input(
        "Ask a question",
        value=pending,
        placeholder="e.g. What are water rudders?",
        label_visibility="collapsed",
        key="query_input",
    )

with col_btn:
    send = st.button("Send →", type="primary")

# ---------------------------------------------------------------------------
# Handle query
# ---------------------------------------------------------------------------

if (send or pending) and query.strip():
    if not PIPELINE_AVAILABLE:
        st.error(f"Pipeline not available: {PIPELINE_ERROR}")
    else:
        st.session_state.messages.append({"role": "user", "content": query.strip()})

        with st.spinner("Retrieving and generating answer..."):
            try:
                result = ask(
                    query.strip(),
                    llm_model=llm_model,
                    embed_model=embed_model,
                    persist_dir=DEFAULT_PERSIST_DIR,
                    collection_name=DEFAULT_COLLECTION,
                    top_k=top_k,
                    fetch_k=fetch_k,
                    use_hyde=use_hyde,
                )

                # Post-process: verify every claim has a source chunk
                checked = None
                display_answer = result["answer"]
                overall_grounded = result["grounded"]

                if verify_claims:
                    checked = check_answer(
                        result["answer"],
                        result["chunks"],
                        refusal_threshold=refusal_threshold,
                    )
                    if checked.verified:
                        display_answer = checked.annotated_answer
                    else:
                        display_answer = (
                            f"⛔ **Answer refused** — insufficient source verification "
                            f"({checked.verified_count}/{checked.claim_count} claims verified, "
                            f"{checked.verification_rate:.0%}).\n\n"
                            f"*The model produced claims that could not be traced back to "
                            f"the retrieved document chunks.*"
                        )
                        overall_grounded = False

                st.session_state.messages.append({
                    "role":              "assistant",
                    "content":           display_answer,
                    "citations":         result["citations"],
                    "latency_ms":        result["latency_ms"],
                    "grounded":          overall_grounded,
                    "chunks":            result["chunks"],
                    "checked":           checked,
                    "hyde_used":         result.get("hyde_used", False),
                })
            except Exception as e:
                st.session_state.messages.append({
                    "role":    "assistant",
                    "content": f"Error: {e}",
                    "grounded": False,
                })

        st.rerun()

# ---------------------------------------------------------------------------
# Retrieved chunks expander (last message only)
# ---------------------------------------------------------------------------

last_assistant = next(
    (m for m in reversed(st.session_state.messages) if m["role"] == "assistant"),
    None,
)
if last_assistant and last_assistant.get("chunks"):
    with st.expander("🔍 Retrieved chunks", expanded=False):
        for i, chunk in enumerate(last_assistant["chunks"], start=1):
            meta = chunk["metadata"]
            page_start = meta.get("page_start", "?")
            page_end   = meta.get("page_end", page_start)
            title      = meta.get("section_title", "Untitled")
            page_label = f"p{page_start}" if page_start == page_end else f"p{page_start}–p{page_end}"
            dist       = chunk.get("distance")
            dist_str   = f"dist={dist:.4f}" if dist else ""

            st.markdown(
                f"**[{i}]** `{page_label}` · {title} · `{dist_str}`"
            )
            st.caption(chunk["document"][:300].replace("\n", " ") + "...")
            if i < len(last_assistant["chunks"]):
                st.markdown("---")