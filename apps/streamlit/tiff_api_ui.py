"""Streamlit UI that talks to the TIFF FastAPI boundary.

Run the API first:
    python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000

Run this UI:
    python -m streamlit run apps/streamlit/tiff_api_ui.py
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any, Mapping

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
from tiff.streamlit_trace_feedback import (  # noqa: E402
    FEEDBACK_CATEGORIES,
    RATINGS,
    answer_quality_hint,
    compact_text,
    feedback_stats,
    flatten_feedback_items,
    infer_trace_target,
    payload_summary,
    step_body,
    step_title,
    trace_steps,
)


QUALITY_LABELS = {
    "ok": "OK",
    "pass": "OK",
    "fail": "Needs attention",
    "needs_attention": "Needs attention",
    "needs attention": "Needs attention",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--api-url", default=os.environ.get("TIFF_API_URL", DEFAULT_API_URL))
    args, _unknown = parser.parse_known_args()
    return args


def _status_label(value: Any) -> str:
    raw = str(value or "unknown").strip().lower()
    return QUALITY_LABELS.get(raw, str(value or "unknown"))


def _wide_button(label: str, **kwargs: Any) -> bool:
    """Render a full-width button on newer Streamlit with fallback for older versions."""

    try:
        return st.button(label, width="stretch", **kwargs)
    except TypeError:  # pragma: no cover - depends on installed Streamlit version
        return st.button(label, use_container_width=True, **kwargs)


def _show_error(exc: Exception) -> None:
    st.error(str(exc))
    st.info(
        "Make sure the FastAPI server is running: "
        "python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000"
    )


def _render_json_expander(label: str, payload: Mapping[str, Any], expanded: bool = False) -> None:
    with st.expander(label, expanded=expanded):
        st.json(dict(payload))


def _metric_row(items: Mapping[str, Any]) -> None:
    cols = st.columns(max(1, min(len(items), 4)))
    for col, (label, value) in zip(cols, items.items()):
        col.metric(label, value)


def _iter_dicts(value: Any):  # noqa: ANN201 - Streamlit helper
    if isinstance(value, Mapping):
        yield value
        for nested in value.values():
            yield from _iter_dicts(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


def _first_str(data: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _source_cards(payload: Mapping[str, Any], *, limit: int = 8) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for node in _iter_dicts(payload):
        page_id = _first_str(node, "page_id", "id")
        source_url = _first_str(node, "source_url", "rescarta_url", "url", "source")
        tiff_path = _first_str(node, "tiff_path", "source_image_path", "tiff", "tiff_uri")
        ocr_path = _first_str(node, "ocr_path", "ocr_text_path", "ocr", "ocr_uri")
        label = _first_str(node, "page_label", "label")
        ata = _first_str(node, "ata", "ata_code")
        if not (page_id or source_url or tiff_path or ocr_path):
            continue
        key = (page_id, source_url, tiff_path)
        if key in seen:
            continue
        seen.add(key)
        cards.append(
            {
                "page_id": page_id,
                "source_url": source_url,
                "tiff_path": tiff_path,
                "ocr_path": ocr_path,
                "label": label,
                "ata": ata,
            }
        )
        if len(cards) >= limit:
            break
    return cards


def _context_snippets(payload: Mapping[str, Any], *, limit: int = 6) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in _iter_dicts(payload):
        summary = _first_str(node, "summary", "short_summary", "context_summary", "text")
        node_id = _first_str(node, "id", "context_id", "page_id")
        node_type = _first_str(node, "node_type", "type")
        score = node.get("score", node.get("context_score"))
        if not summary:
            continue
        looks_contextual = "context" in node_id.lower() or "context" in node_type.lower() or "page_context" in node_type.lower()
        if not looks_contextual and len(summary) < 45:
            continue
        if summary in seen:
            continue
        seen.add(summary)
        snippets.append({"id": node_id, "summary": summary, "score": score})
        if len(snippets) >= limit:
            break
    return snippets


def _render_summary(payload: Mapping[str, Any], title: str = "Summary") -> None:
    summary = payload_summary(payload)
    if not summary:
        return
    st.markdown(f"### {title}")
    _metric_row({key.replace("_", " ").title(): value for key, value in summary.items()})


def _render_source_cards(payload: Mapping[str, Any], *, title: str = "Source evidence") -> None:
    cards = _source_cards(payload)
    if not cards:
        return
    st.markdown(f"### {title}")
    for idx, card in enumerate(cards, start=1):
        with st.container(border=True):
            st.markdown(
                f"**{idx}. Page:** `{card.get('page_id') or '-'}`  "
                f"**Label:** `{card.get('label') or '-'}`  "
                f"**ATA:** `{card.get('ata') or '-'}`"
            )
            if card.get("source_url"):
                st.markdown(f"**Source:** {card['source_url']}")
            if card.get("tiff_path"):
                st.caption(f"TIFF: {card['tiff_path']}")
            if card.get("ocr_path"):
                st.caption(f"OCR: {card['ocr_path']}")


def _render_context_snippets(payload: Mapping[str, Any]) -> None:
    snippets = _context_snippets(payload)
    if not snippets:
        return
    st.markdown("### AI page context")
    for item in snippets:
        score = item.get("score")
        score_text = f"score={score}" if score is not None else "score=-"
        st.info(f"{item.get('summary', '')}\n\n{score_text}")


def _render_trace_steps(payload: Mapping[str, Any]) -> None:
    steps = trace_steps(payload)
    if not steps:
        return
    st.markdown("### Trace path")
    for idx, step in enumerate(steps[:60], start=1):
        with st.container(border=True):
            st.markdown(f"**{step_title(step, idx)}**")
            details = step_body(step)
            if details:
                st.json(details)
    if len(steps) > 60:
        st.caption(f"... {len(steps) - 60} more trace steps not shown")


def _save_answer(question: str, payload: dict[str, Any]) -> None:
    answer = extract_answer_text(payload)
    st.session_state["last_question"] = question
    st.session_state["last_answer_text"] = answer
    st.session_state["last_answer_payload"] = payload
    target = infer_trace_target(question, answer)
    st.session_state["last_trace_target"] = target


def _trace_last_answer(api_url: str) -> None:
    target = st.session_state.get("last_trace_target") or {}
    kind = target.get("type")
    value = target.get("value")
    if not kind or not value:
        st.warning("No part, page, or ATA was detected in the last answer.")
        return
    try:
        if kind == "part":
            st.session_state["trace_payload"] = trace_part(api_url, value)
            st.session_state["trace_label"] = f"Part trace: {value}"
        elif kind == "page":
            st.session_state["trace_payload"] = trace_page(api_url, value)
            st.session_state["trace_label"] = f"Page trace: {value}"
        else:
            st.session_state["lookup_payload"] = get_ata(api_url, value)
            st.info("ATA evidence loaded in the Lookup tab.")
    except TiffApiError as exc:
        _show_error(exc)


def main() -> None:
    args = _parse_args()
    st.set_page_config(page_title="TIFF RAG API UI", layout="wide")

    st.title("TIFF RAG API UI")
    st.caption("Ask questions, inspect trace paths, and submit feedback through the FastAPI boundary.")

    with st.sidebar:
        st.header("API connection")
        api_url = normalize_api_url(st.text_input("FastAPI URL", value=args.api_url))
        timeout_seconds = st.number_input("Ask timeout seconds", min_value=10, max_value=600, value=120, step=10)
        st.code("python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000")
        if _wide_button("Check /status"):
            try:
                st.session_state["status_payload"] = get_status(api_url)
            except TiffApiError as exc:
                _show_error(exc)

    try:
        status_payload = st.session_state.get("status_payload") or get_status(api_url, timeout_seconds=10)
        st.session_state["status_payload"] = status_payload
        status_summary = status_payload.get("summary") if isinstance(status_payload.get("summary"), dict) else status_payload
        if isinstance(status_summary, dict):
            _metric_row(
                {
                    "Quality": _status_label(status_payload.get("status", status_summary.get("status"))),
                    "Pages": status_summary.get("document_graph_page_nodes", status_summary.get("pages", "-")),
                    "Contexts": status_summary.get("document_graph_context_nodes", "-"),
                    "Sources": status_summary.get("document_graph_source_link_nodes", "-"),
                }
            )
    except Exception:
        st.warning("FastAPI is not reachable. Start it before using the UI.")

    ask_tab, lookup_tab, trace_tab, feedback_tab, status_tab = st.tabs(
        ["Ask", "Lookup", "Trace / why this answer?", "Feedback", "Status / Quality"]
    )

    with ask_tab:
        st.subheader("Ask a question")
        question = st.text_area("Question", value=st.session_state.get("last_question", "What is part number 120-37313-001?"), height=90)
        if _wide_button("Ask API", type="primary"):
            try:
                with st.spinner("Calling /ask..."):
                    payload = ask_question(api_url, question, timeout_seconds=float(timeout_seconds))
                _save_answer(question, payload)
            except TiffApiError as exc:
                _show_error(exc)

        if "last_answer_payload" in st.session_state:
            payload = st.session_state["last_answer_payload"]
            st.markdown("### Answer")
            st.markdown(st.session_state.get("last_answer_text", ""))
            c1, c2, c3 = st.columns(3)
            if c1.button("Trace this answer", width="stretch"):
                _trace_last_answer(api_url)
            if c2.button("Copy into feedback", width="stretch"):
                st.session_state["feedback_question"] = st.session_state.get("last_question", "")
                st.session_state["feedback_answer"] = st.session_state.get("last_answer_text", "")
                st.success("Copied to Feedback tab.")
            with c3.popover("Detected trace target"):
                st.json(st.session_state.get("last_trace_target", {}))
            _render_source_cards(payload, title="Sources from answer payload")
            _render_context_snippets(payload)
            _render_json_expander("Raw /ask JSON", payload)

    with lookup_tab:
        st.subheader("Lookup")
        lookup_type = st.radio("Lookup type", ["Part", "Page", "ATA", "Summary"], horizontal=True)
        try:
            if lookup_type == "Part":
                part = st.text_input("Part number", value="120-37313-001")
                c1, c2 = st.columns(2)
                if c1.button("Lookup part", width="stretch"):
                    st.session_state["lookup_payload"] = get_part(api_url, part)
                if c2.button("Trace part", width="stretch"):
                    st.session_state["trace_payload"] = trace_part(api_url, part)
                    st.session_state["trace_label"] = f"Part trace: {part}"
            elif lookup_type == "Page":
                page_id = st.text_input("Page ID", value="t_p_120_1176_p000083")
                c1, c2 = st.columns(2)
                if c1.button("Lookup page", width="stretch"):
                    st.session_state["lookup_payload"] = get_page(api_url, page_id)
                if c2.button("Trace page", width="stretch"):
                    st.session_state["trace_payload"] = trace_page(api_url, page_id)
                    st.session_state["trace_label"] = f"Page trace: {page_id}"
            elif lookup_type == "ATA":
                ata = st.text_input("ATA code", value="25-21-00")
                if _wide_button("Lookup ATA"):
                    st.session_state["lookup_payload"] = get_ata(api_url, ata)
            else:
                if _wide_button("Load organization summary"):
                    st.session_state["lookup_payload"] = get_organization_summary(api_url)
        except TiffApiError as exc:
            _show_error(exc)

        if "lookup_payload" in st.session_state:
            payload = st.session_state["lookup_payload"]
            _render_summary(payload)
            _render_source_cards(payload)
            _render_context_snippets(payload)
            _render_json_expander("Raw lookup JSON", payload)

    with trace_tab:
        st.subheader("Trace / why this answer?")
        st.caption("Shows how a part, page, or vector result resolves back to document, ATA, source, and AI context.")
        trace_type = st.radio("Trace type", ["Part", "Page", "Vector payload", "Last answer"], horizontal=True)
        try:
            if trace_type == "Part":
                part = st.text_input("Trace part", value="120-37313-001")
                if _wide_button("Trace part"):
                    st.session_state["trace_payload"] = trace_part(api_url, part)
                    st.session_state["trace_label"] = f"Part trace: {part}"
            elif trace_type == "Page":
                page_id = st.text_input("Trace page", value="t_p_120_1176_p000083")
                if _wide_button("Trace page"):
                    st.session_state["trace_payload"] = trace_page(api_url, page_id)
                    st.session_state["trace_label"] = f"Page trace: {page_id}"
            elif trace_type == "Vector payload":
                page_id = st.text_input("Vector payload page_id", value="t_p_120_1176_p000495")
                chunk_id = st.text_input("Vector payload chunk_id", value="chunk_t_p_120_1176_p000495_001")
                score = st.number_input("Vector score", min_value=0.0, max_value=1.0, value=0.635, step=0.001, format="%.3f")
                if _wide_button("Trace vector payload"):
                    st.session_state["trace_payload"] = trace_vector(api_url, page_id=page_id, chunk_id=chunk_id, score=float(score))
                    st.session_state["trace_label"] = f"Vector trace: {page_id}"
            else:
                if _wide_button("Trace last answer"):
                    _trace_last_answer(api_url)
        except TiffApiError as exc:
            _show_error(exc)

        if "trace_payload" in st.session_state:
            payload = st.session_state["trace_payload"]
            st.markdown(f"### {st.session_state.get('trace_label', 'Trace result')}")
            _render_summary(payload, title="Trace summary")
            _render_trace_steps(payload)
            _render_source_cards(payload, title="Source cards")
            _render_context_snippets(payload)
            _render_json_expander("Raw trace JSON", payload)

    with feedback_tab:
        st.subheader("Feedback")
        st.caption("Feedback is stored for review. It does not automatically change source facts.")
        feedback_question = st.text_area("Question being rated", value=st.session_state.get("feedback_question", st.session_state.get("last_question", "")), height=80)
        feedback_answer = st.text_area("Answer being rated", value=st.session_state.get("feedback_answer", st.session_state.get("last_answer_text", "")), height=180)
        c1, c2 = st.columns(2)
        with c1:
            rating = st.selectbox("Rating", RATINGS)
        with c2:
            category = st.selectbox("Category", FEEDBACK_CATEGORIES)
        st.caption(answer_quality_hint(rating, category))
        reason = st.text_area("Reason/comment", value="", height=80)
        if _wide_button("Submit feedback", type="primary"):
            try:
                payload = submit_feedback(api_url, question=feedback_question, answer=feedback_answer, rating=rating, category=category, reason=reason)
                st.success("Feedback saved")
                st.json(payload)
            except TiffApiError as exc:
                _show_error(exc)

        c3, c4 = st.columns(2)
        if c3.button("Load feedback summary", width="stretch"):
            try:
                st.session_state["feedback_summary"] = get_feedback_summary(api_url)
            except TiffApiError as exc:
                _show_error(exc)
        if c4.button("Use last answer", width="stretch"):
            st.session_state["feedback_question"] = st.session_state.get("last_question", "")
            st.session_state["feedback_answer"] = st.session_state.get("last_answer_text", "")
            st.rerun()
        if "feedback_summary" in st.session_state:
            feedback_payload = st.session_state["feedback_summary"]
            stats = feedback_stats(feedback_payload)
            if stats:
                st.markdown("### Feedback stats")
                _metric_row(stats)
            rows = flatten_feedback_items(feedback_payload)
            if rows:
                st.markdown("### Recent feedback")
                st.dataframe(rows, width="stretch")
            _render_json_expander("Raw feedback summary", feedback_payload)

    with status_tab:
        st.subheader("Status / quality")
        if _wide_button("Refresh status", type="primary"):
            try:
                st.session_state["status_payload"] = get_status(api_url)
            except TiffApiError as exc:
                _show_error(exc)
        payload = st.session_state.get("status_payload", {})
        if isinstance(payload, dict) and payload:
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else payload
            if isinstance(summary, dict):
                _metric_row(
                    {
                        "Status": _status_label(payload.get("status", summary.get("status", "unknown"))),
                        "Pages": summary.get("document_graph_page_nodes", summary.get("pages", "-")),
                        "Contexts": summary.get("document_graph_context_nodes", "-"),
                        "User fails": summary.get("user_query_fail", "-"),
                    }
                )
            _render_json_expander("Raw status JSON", payload, expanded=True)
        else:
            st.info("Click Refresh status to load the API quality summary.")


if __name__ == "__main__":
    main()
