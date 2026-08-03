#!/usr/bin/env python3
"""Streamlit UI for the local TIFF organization/RAG backend.

Run from repo root:

    python scripts/maintenance/ingestion/check_tiff_ui_ready.py --strict
    python -m streamlit run apps/streamlit/tiff_rag_ui.py

This UI is intentionally local/read-only. It consumes organization export JSON
for browsing and calls the existing ask_tiff_rag.py CLI for answering.
"""

from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.document_organization_query import load_export, summarize_export  # noqa: E402
from tiff.streamlit_ui_backend import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    DEFAULT_EXPORT_DIR,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_QUALITY_PATH,
    ata_result_records,
    format_ata_for_ui,
    format_page_for_ui,
    format_part_for_ui,
    load_ui_status,
    page_result_records,
    parse_rag_cli_stdout,
    part_result_records,
    part_source_records,
    run_rag_question,
    search_ata,
    search_pages,
    search_parts,
)


@st.cache_data(show_spinner=False)
def _load_export_cached(export_dir: str):
    export = load_export(export_dir)
    return export, summarize_export(export)


@st.cache_data(show_spinner=False)
def _load_status_cached(export_dir: str, manifest_path: str, quality_path: str):
    return load_ui_status(export_dir=export_dir, manifest_path=manifest_path, quality_path=quality_path)


def main() -> None:
    st.set_page_config(page_title="HEICO TIFF Search", layout="wide")
    st.title("HEICO TIFF Search + RAG")
    st.caption("Local MVP UI over the organization export, source links, quality gate, and ask_tiff_rag.py.")

    with st.sidebar:
        st.header("Local paths")
        export_dir = st.text_input("Organization export", value=str(DEFAULT_EXPORT_DIR))
        config_path = st.text_input("Config", value=str(DEFAULT_CONFIG_PATH))
        manifest_path = st.text_input("Pipeline manifest", value=str(DEFAULT_MANIFEST_PATH))
        quality_path = st.text_input("Quality gate JSON", value=str(DEFAULT_QUALITY_PATH))
        if st.button("Refresh UI data"):
            st.cache_data.clear()
            st.rerun()

    try:
        export, summary = _load_export_cached(export_dir)
    except Exception as exc:
        st.error(f"Organization export is not available: {exc}")
        st.stop()

    status = _load_status_cached(export_dir, manifest_path, quality_path)

    tab_status, tab_browse, tab_ask, tab_sources = st.tabs(
        ["Status", "Browse", "Ask", "Sources"]
    )

    with tab_status:
        st.subheader("Backend health")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("UI ready", "OK" if status.ok else "Review")
        c2.metric("Quality gate", status.quality_status or "-")
        c3.metric("Pipeline", status.manifest_status or "-")
        c4.metric("Incremental smoke", "OK" if status.incremental_smoke_ok else "Review")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Pages", status.pages or 0)
        c2.metric("ATA groups", status.ata_groups or 0)
        c3.metric("Parts", status.parts or 0)
        c4.metric("Part mentions", status.part_mentions or 0)

        c1, c2, c3 = st.columns(3)
        c1.metric("Local source links", "OK" if status.source_local_review_ready else "Review")
        c2.metric("Real ResCarta", "Ready" if status.real_rescarta_ready else "Placeholder")
        c3.metric("Empty OCR files", status.ocr_empty_files or 0)

        if status.errors:
            st.warning("\n".join(status.errors))
        with st.expander("Raw organization summary"):
            st.json(summary)

    with tab_browse:
        st.subheader("Browse organized documents")
        mode = st.radio("Lookup type", ["Part", "ATA", "Page"], horizontal=True)
        default_query = "120-37313-001" if mode == "Part" else "25-21-00" if mode == "ATA" else "t_p_120_1176_p000042"
        query = st.text_input("Search", value=default_query)
        limit = st.slider("Results", min_value=1, max_value=25, value=5)
        if st.button("Search organization", type="primary"):
            if mode == "Part":
                rows = search_parts(export, query, limit=limit)
                if not rows:
                    st.info("No part matches.")
                else:
                    st.dataframe(part_result_records(rows), width="stretch", hide_index=True)
                    for row in rows:
                        label = format_part_for_ui(row).splitlines()[0]
                        with st.expander(label):
                            source_rows = part_source_records(row, limit=limit)
                            if source_rows:
                                st.dataframe(source_rows, width="stretch", hide_index=True)
                            with st.expander("Raw part record"):
                                st.json(row)
            elif mode == "ATA":
                rows = search_ata(export, query, limit=limit)
                if not rows:
                    st.info("No ATA matches.")
                else:
                    st.dataframe(ata_result_records(rows), width="stretch", hide_index=True)
                    for row in rows:
                        with st.expander(format_ata_for_ui(row)):
                            st.json(row)
            else:
                rows = search_pages(export, query, limit=limit)
                if not rows:
                    st.info("No page matches.")
                else:
                    st.dataframe(page_result_records(rows), width="stretch", hide_index=True)
                    for row in rows:
                        with st.expander(format_page_for_ui(row).splitlines()[0]):
                            st.json(row)

    with tab_ask:
        st.subheader("Ask the TIFF assistant")
        st.caption("Exact part/ATA queries should stay deterministic. Broad summaries may use Gemma and take longer.")
        examples = [
            "What is part number 120-37313-001?",
            "What is part number AM03078-22?",
            "Where is HOLDER, MAGAZINE mentioned?",
            "Find evidence for ATA 25-21-00.",
            "Summarize passenger seat back crack reinforcement using source evidence.",
        ]
        selected = st.selectbox("Example", examples)
        question = st.text_area("Question", value=selected, height=90)
        timeout_seconds = st.slider("Timeout seconds", min_value=30, max_value=600, value=240, step=30)
        if st.button("Ask", type="primary"):
            with st.spinner("Running ask_tiff_rag.py..."):
                try:
                    result = run_rag_question(question, config_path=config_path, timeout_seconds=timeout_seconds)
                except Exception as exc:
                    st.error(f"Failed to run ask_tiff_rag.py: {exc}")
                else:
                    view = parse_rag_cli_stdout(result.stdout or "")
                    if result.returncode == 0:
                        st.success("Answer complete")
                    else:
                        st.error(f"ask_tiff_rag.py exited with {result.returncode}")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("LLM used", view.llm_used or "-")
                    c2.metric("Embeddings used", view.embeddings_used or "-")
                    c3.metric("Exit code", result.returncode)
                    if view.answer:
                        st.markdown("#### Answer")
                        st.text(view.answer)
                    if view.sources:
                        with st.expander("Sources"):
                            st.text(view.sources)
                    with st.expander("Raw CLI output"):
                        st.code(result.stdout or "", language="text")
                    if result.stderr:
                        with st.expander("stderr"):
                            st.code(result.stderr, language="text")

    with tab_sources:
        st.subheader("Source/page lookup")
        st.caption("Use this to verify that source URL, TIFF path, and OCR path are visible for a page.")
        page_query = st.text_input("Page id or label", value="t_p_120_1176_p000042", key="source_page_query")
        if st.button("Find page sources"):
            rows = search_pages(export, page_query, limit=10)
            if not rows:
                st.info("No page matches.")
            else:
                st.dataframe(page_result_records(rows), width="stretch", hide_index=True)
                for row in rows:
                    with st.expander(format_page_for_ui(row).splitlines()[0]):
                        st.json(row)


if __name__ == "__main__":
    main()
