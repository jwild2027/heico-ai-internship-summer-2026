"""Streamlit UI that talks to the TIFF FastAPI boundary.

Run the API first:
    python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000

Run this UI:
    python -m streamlit run apps/streamlit/tiff_api_ui.py
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

import streamlit as st

# Make the repo root importable when Streamlit executes this file directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.streamlit_api_client import (  # noqa: E402
    DEFAULT_API_URL,
    TiffApiError,
    ask_question,
    extract_answer_text,
    get_ata,
    get_feedback_summary,
    get_organization_summary,
    get_page,
    get_part,
    get_status,
    normalize_api_url,
    submit_feedback,
    trace_page,
    trace_part,
    trace_vector,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--api-url", default=os.environ.get("TIFF_API_URL", DEFAULT_API_URL))
    args, _unknown = parser.parse_known_args()
    return args


def _show_error(exc: Exception) -> None:
    st.error(str(exc))
    st.info("Make sure the FastAPI server is running: python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000")


def _render_json_expander(label: str, payload: dict[str, Any], expanded: bool = False) -> None:
    with st.expander(label, expanded=expanded):
        st.json(payload)


def _metric_row(items: dict[str, Any]) -> None:
    cols = st.columns(max(1, min(len(items), 4)))
    for col, (label, value) in zip(cols, items.items()):
        col.metric(label, value)


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Return small status/count fields for a quick top-level summary."""

    wanted = (
        "status",
        "part_number",
        "nomenclature",
        "page_id",
        "document",
        "ata",
        "source_link_present",
        "context_present",
        "context_score",
        "total_pages_found",
        "pages",
        "parts",
        "page_context_nodes",
        "source_link_nodes",
    )
    out: dict[str, Any] = {}
    for key in wanted:
        if key in payload and not isinstance(payload[key], (dict, list)):
            out[key] = payload[key]
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in wanted:
            if key in summary and not isinstance(summary[key], (dict, list)):
                out[key] = summary[key]
    return out


def main() -> None:
    args = _parse_args()
    st.set_page_config(page_title="TIFF RAG API UI", layout="wide")

    st.title("TIFF RAG API UI")
    st.caption("Streamlit frontend using the FastAPI boundary: ask, lookup, trace, feedback, and quality status.")

    with st.sidebar:
        st.header("API connection")
        api_url = normalize_api_url(st.text_input("FastAPI URL", value=args.api_url))
        timeout_seconds = st.number_input("Ask timeout seconds", min_value=10, max_value=600, value=120, step=10)
        st.code("python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000")
        if st.button("Check /status", use_container_width=True):
            try:
                st.session_state["last_status"] = get_status(api_url)
            except TiffApiError as exc:
                _show_error(exc)
        if "last_status" in st.session_state:
            status_payload = st.session_state["last_status"]
            st.success(f"API status: {status_payload.get('status', 'unknown')}")

    tabs = st.tabs(["Ask", "Lookup", "Trace", "Feedback", "Status / Quality"])

    with tabs[0]:
        st.subheader("Ask a question")
        default_question = st.session_state.get("last_question", "What is part number 120-37313-001?")
        question = st.text_area("Question", value=default_question, height=90)
        if st.button("Ask API", type="primary"):
            try:
                with st.spinner("Calling /ask..."):
                    payload = ask_question(api_url, question, timeout_seconds=float(timeout_seconds))
                st.session_state["last_question"] = question
                st.session_state["last_answer_payload"] = payload
                st.session_state["last_answer_text"] = extract_answer_text(payload)
            except TiffApiError as exc:
                _show_error(exc)

        if "last_answer_payload" in st.session_state:
            payload = st.session_state["last_answer_payload"]
            st.markdown("### Answer")
            st.text_area("Answer text", value=st.session_state.get("last_answer_text", ""), height=280)
            summary = _payload_summary(payload)
            if summary:
                st.markdown("### Quick fields")
                st.json(summary)
            _render_json_expander("Raw /ask JSON", payload)

    with tabs[1]:
        st.subheader("Organization lookup")
        lookup_type = st.radio("Lookup type", ["Part", "Page", "ATA", "Summary"], horizontal=True)
        if lookup_type == "Part":
            part = st.text_input("Part number", value="120-37313-001")
            if st.button("Lookup part"):
                try:
                    payload = get_part(api_url, part)
                    st.session_state["lookup_payload"] = payload
                except TiffApiError as exc:
                    _show_error(exc)
        elif lookup_type == "Page":
            page_id = st.text_input("Page ID", value="t_p_120_1176_p000083")
            if st.button("Lookup page"):
                try:
                    payload = get_page(api_url, page_id)
                    st.session_state["lookup_payload"] = payload
                except TiffApiError as exc:
                    _show_error(exc)
        elif lookup_type == "ATA":
            ata = st.text_input("ATA code", value="25-21-00")
            if st.button("Lookup ATA"):
                try:
                    payload = get_ata(api_url, ata)
                    st.session_state["lookup_payload"] = payload
                except TiffApiError as exc:
                    _show_error(exc)
        else:
            if st.button("Load organization summary"):
                try:
                    payload = get_organization_summary(api_url)
                    st.session_state["lookup_payload"] = payload
                except TiffApiError as exc:
                    _show_error(exc)

        if "lookup_payload" in st.session_state:
            payload = st.session_state["lookup_payload"]
            summary = _payload_summary(payload)
            if summary:
                st.markdown("### Summary")
                st.json(summary)
            _render_json_expander("Raw lookup JSON", payload, expanded=True)

    with tabs[2]:
        st.subheader("Trace / why this result?")
        trace_type = st.radio("Trace type", ["Part", "Page", "Vector payload"], horizontal=True)
        if trace_type == "Part":
            part = st.text_input("Trace part", value="120-37313-001", key="trace_part_input")
            if st.button("Trace part"):
                try:
                    st.session_state["trace_payload"] = trace_part(api_url, part)
                except TiffApiError as exc:
                    _show_error(exc)
        elif trace_type == "Page":
            page_id = st.text_input("Trace page", value="t_p_120_1176_p000083", key="trace_page_input")
            if st.button("Trace page"):
                try:
                    st.session_state["trace_payload"] = trace_page(api_url, page_id)
                except TiffApiError as exc:
                    _show_error(exc)
        else:
            page_id = st.text_input("Vector payload page_id", value="t_p_120_1176_p000495")
            chunk_id = st.text_input("Vector payload chunk_id", value="chunk_t_p_120_1176_p000495_001")
            score = st.number_input("Vector score", min_value=0.0, max_value=1.0, value=0.635, step=0.001, format="%.3f")
            if st.button("Trace vector payload"):
                try:
                    st.session_state["trace_payload"] = trace_vector(api_url, page_id=page_id, chunk_id=chunk_id, score=float(score))
                except TiffApiError as exc:
                    _show_error(exc)

        if "trace_payload" in st.session_state:
            payload = st.session_state["trace_payload"]
            summary = _payload_summary(payload)
            if summary:
                st.markdown("### Trace summary")
                st.json(summary)
            path = payload.get("path") or payload.get("trace", {}).get("path") if isinstance(payload.get("trace"), dict) else None
            if isinstance(path, list):
                st.markdown("### Path")
                for idx, step in enumerate(path, start=1):
                    st.write(f"{idx}. {step}")
            _render_json_expander("Raw trace JSON", payload)

    with tabs[3]:
        st.subheader("Feedback")
        st.caption("Store feedback against the answer/question. This does not automatically change facts.")
        feedback_question = st.text_area("Question being rated", value=st.session_state.get("last_question", ""), height=80)
        feedback_answer = st.text_area("Answer being rated", value=st.session_state.get("last_answer_text", ""), height=140)
        cols = st.columns(3)
        with cols[0]:
            rating = st.selectbox("Rating", ["up", "down", "neutral", "1", "2", "3", "4", "5"])
        with cols[1]:
            category = st.selectbox(
                "Category",
                ["useful", "wrong_answer", "wrong_source", "missing_source", "incomplete", "too_verbose", "ocr_issue", "other"],
            )
        with cols[2]:
            st.write("")
            st.write("")
            submit = st.button("Submit feedback", type="primary", use_container_width=True)
        reason = st.text_input("Reason/comment", value="")
        if submit:
            try:
                payload = submit_feedback(
                    api_url,
                    question=feedback_question,
                    answer=feedback_answer,
                    rating=rating,
                    category=category,
                    reason=reason,
                )
                st.success("Feedback saved")
                st.json(payload)
            except TiffApiError as exc:
                _show_error(exc)
        if st.button("Load feedback summary"):
            try:
                st.session_state["feedback_summary"] = get_feedback_summary(api_url)
            except TiffApiError as exc:
                _show_error(exc)
        if "feedback_summary" in st.session_state:
            _render_json_expander("Feedback summary", st.session_state["feedback_summary"], expanded=True)

    with tabs[4]:
        st.subheader("Status / quality")
        if st.button("Refresh status", type="primary"):
            try:
                st.session_state["status_payload"] = get_status(api_url)
            except TiffApiError as exc:
                _show_error(exc)
        if "status_payload" in st.session_state:
            payload = st.session_state["status_payload"]
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else payload
            if isinstance(summary, dict):
                metrics = {
                    "Status": payload.get("status", summary.get("status", "unknown")),
                    "Pages": summary.get("document_graph_page_nodes", summary.get("pages", "-")),
                    "Contexts": summary.get("document_graph_context_nodes", "-"),
                    "User fails": summary.get("user_query_fail", "-"),
                }
                _metric_row(metrics)
            _render_json_expander("Raw status JSON", payload, expanded=True)
        else:
            st.info("Click Refresh status to load the API quality summary.")


if __name__ == "__main__":
    main()
