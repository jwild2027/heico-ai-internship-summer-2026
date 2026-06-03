from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import uuid
import webbrowser
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_FEEDBACK_DIR = TRACE_NET_DIR / "feedback"

_ALLOWED_RATINGS = {"thumbs_up", "thumbs_down", "neutral"}
_PAGE_RE = re.compile(r"t_p_[0-9a-zA-Z_]+_p\d{6}")
_PART_RE = re.compile(r"\b[A-Z0-9]{1,4}-[A-Z0-9]{2,8}-[A-Z0-9]{1,8}\b")


@dataclass(frozen=True)
class FeedbackPaths:
    trace_net_dir: Path = TRACE_NET_DIR
    output_dir: Path = DEFAULT_FEEDBACK_DIR

    @property
    def ask_summary(self) -> Path:
        return self.trace_net_dir / "ask" / "trace_net_ask_summary.json"

    @property
    def answer_json(self) -> Path:
        return self.trace_net_dir / "answers" / "trace_net_answer_draft.json"

    @property
    def answer_summary(self) -> Path:
        return self.trace_net_dir / "answers" / "trace_net_answer_summary.json"

    @property
    def answer_evidence(self) -> Path:
        return self.trace_net_dir / "answers" / "trace_net_answer_evidence.jsonl"

    @property
    def grouped_results(self) -> Path:
        return self.trace_net_dir / "search" / "trace_net_search_grouped_results.jsonl"

    @property
    def search_summary(self) -> Path:
        return self.trace_net_dir / "search" / "trace_net_search_summary.json"

    @property
    def candidate_chunks(self) -> Path:
        return self.trace_net_dir / "rag_candidates" / "rag_candidate_chunks.jsonl"

    @property
    def citation_records(self) -> Path:
        return self.trace_net_dir / "citations" / "trace_net_source_citations.jsonl"

    @property
    def feedback_events(self) -> Path:
        return self.output_dir / "feedback_events.jsonl"

    @property
    def summary(self) -> Path:
        return self.output_dir / "feedback_summary.json"

    @property
    def graph_nodes(self) -> Path:
        return self.output_dir / "feedback_graph_nodes.json"

    @property
    def graph_edges(self) -> Path:
        return self.output_dir / "feedback_graph_edges.json"

    @property
    def policy_signals(self) -> Path:
        return self.output_dir / "feedback_policy_signals.jsonl"

    @property
    def review_md(self) -> Path:
        return self.output_dir / "feedback_review.md"

    @property
    def review_html(self) -> Path:
        return self.output_dir / "feedback_review.html"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def _split_values(values: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    if not values:
        return out
    for value in values:
        for part in str(value).split(","):
            part = part.strip()
            if part:
                out.append(part)
    return out


def _normalize_rating(rating: str) -> str:
    rating = (rating or "").strip().lower().replace("-", "_")
    aliases = {
        "up": "thumbs_up",
        "thumb_up": "thumbs_up",
        "thumbs_up": "thumbs_up",
        "positive": "thumbs_up",
        "good": "thumbs_up",
        "down": "thumbs_down",
        "thumb_down": "thumbs_down",
        "thumbs_down": "thumbs_down",
        "negative": "thumbs_down",
        "bad": "thumbs_down",
        "neutral": "neutral",
        "meh": "neutral",
    }
    rating = aliases.get(rating, rating)
    if rating not in _ALLOWED_RATINGS:
        raise ValueError(f"Unsupported rating {rating!r}; choose one of {sorted(_ALLOWED_RATINGS)}")
    return rating


def _normalize_page_ids(values: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    for value in _split_values(values):
        match = _PAGE_RE.search(value)
        out.append(match.group(0) if match else value)
    return sorted(dict.fromkeys(out))


def _normalize_candidate_ids(values: Optional[Sequence[str]]) -> List[str]:
    return sorted(dict.fromkeys(_split_values(values)))


def _normalize_reason_codes(values: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    for value in _split_values(values):
        code = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
        if code:
            out.append(code)
    return sorted(dict.fromkeys(out))


def _sha1_text(text: str, length: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:length]


def _query_fingerprint(query: str = "", part_number: str = "", page_id: str = "") -> str:
    if part_number:
        return "part_number:" + part_number.upper().strip()
    if page_id:
        return "page:" + page_id.strip()
    text = (query or "").strip()
    if not text:
        return "query:unknown"
    part_match = _PART_RE.search(text.upper())
    if part_match:
        return "part_number:" + part_match.group(0)
    page_match = _PAGE_RE.search(text)
    if page_match:
        return "page:" + page_match.group(0)
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return "query:" + "_".join(tokens[:12]) if tokens else "query:" + _sha1_text(text)


def _infer_latest_context(paths: FeedbackPaths) -> Dict[str, Any]:
    ask_summary = _read_json(paths.ask_summary, {}) or {}
    answer_json = _read_json(paths.answer_json, {}) or {}
    answer_summary = _read_json(paths.answer_summary, {}) or {}
    search_summary = _read_json(paths.search_summary, {}) or {}
    grouped_results = _read_jsonl(paths.grouped_results)
    evidence_records = _read_jsonl(paths.answer_evidence)

    query = (
        ask_summary.get("query")
        or ask_summary.get("effective_query")
        or search_summary.get("query")
        or search_summary.get("effective_query")
        or answer_summary.get("query")
        or ""
    )
    part_number = ask_summary.get("part_number") or search_summary.get("part_number") or ""
    page_id = ask_summary.get("page_id") or search_summary.get("page_id") or ""

    context_key = json.dumps(
        {
            "query": query,
            "part_number": part_number,
            "page_id": page_id,
            "answer_pages": answer_summary.get("answer_page_records") or answer_json.get("answer_page_records"),
            "grouped_pages": len(grouped_results),
        },
        sort_keys=True,
    )
    ask_run_id = ask_summary.get("ask_run_id") or ask_summary.get("run_id") or "ask:" + _sha1_text(context_key)
    answer_id = answer_json.get("answer_id") or answer_summary.get("answer_id") or "answer:" + _sha1_text(context_key)

    grouped_page_ids = []
    for record in grouped_results:
        page = record.get("page_id") or record.get("page")
        if page:
            grouped_page_ids.append(page)

    return {
        "ask_summary_present": paths.ask_summary.exists(),
        "answer_json_present": paths.answer_json.exists(),
        "answer_summary_present": paths.answer_summary.exists(),
        "grouped_results_present": paths.grouped_results.exists(),
        "answer_evidence_present": paths.answer_evidence.exists(),
        "ask_run_id": ask_run_id,
        "answer_id": answer_id,
        "query": query,
        "part_number": part_number,
        "page_id": page_id,
        "query_fingerprint": _query_fingerprint(query, part_number, page_id),
        "grouped_page_ids": sorted(dict.fromkeys(grouped_page_ids)),
        "grouped_page_count": len(set(grouped_page_ids)),
        "answer_evidence_records": len(evidence_records),
        "source_artifacts": {
            "ask_summary": str(paths.ask_summary),
            "answer_json": str(paths.answer_json),
            "answer_summary": str(paths.answer_summary),
            "grouped_results": str(paths.grouped_results),
            "answer_evidence": str(paths.answer_evidence),
        },
        "pipeline_versions": {
            "ask": ask_summary.get("version") or "unknown",
            "answer": answer_summary.get("version") or answer_json.get("version") or "unknown",
            "search": search_summary.get("version") or "unknown",
        },
    }


def _validate_feedback_context(
    *,
    context: Dict[str, Any],
    query_fingerprint: str,
    affected_pages: Sequence[str],
    expected_pages: Sequence[str],
    affected_candidates: Sequence[str],
    explicit_context_supplied: bool,
    allow_unvalidated_policy_signal: bool = False,
) -> Dict[str, Any]:
    """Validate whether feedback can safely become a ranking/retrieval signal.

    Feedback is always stored. It only becomes policy-signal eligible when it is
    linked to the current ask/answer context well enough that a page-level boost
    or demotion is meaningful. This prevents accidental use of feedback recorded
    against the wrong latest ask run.
    """
    latest_qfp = context.get("query_fingerprint") or "query:unknown"
    grouped_pages = set(context.get("grouped_page_ids") or [])
    affected_set = set(affected_pages or [])
    expected_set = set(expected_pages or [])
    warnings: List[str] = []

    query_fingerprint_matches_latest = query_fingerprint == latest_qfp
    if not query_fingerprint_matches_latest:
        if explicit_context_supplied:
            warnings.append("explicit_query_context_differs_from_latest_ask")
        else:
            warnings.append("query_fingerprint_mismatch")

    if not context.get("ask_summary_present"):
        warnings.append("missing_ask_summary")
    if not context.get("answer_summary_present") and not context.get("answer_json_present"):
        warnings.append("missing_answer_artifact")
    if not context.get("grouped_results_present"):
        warnings.append("missing_grouped_results")

    affected_not_in_answer = sorted(affected_set - grouped_pages) if grouped_pages else sorted(affected_set)
    expected_not_in_answer = sorted(expected_set - grouped_pages) if grouped_pages else sorted(expected_set)
    if affected_not_in_answer:
        warnings.append("affected_page_not_in_answer")
    if expected_not_in_answer:
        warnings.append("expected_page_not_in_answer")

    # Candidate-level validation will be stricter when answer evidence/candidate IDs
    # are stable across the full UI; for v1.1 candidate IDs are recorded but not used
    # as a hard validity failure unless no page context exists at all.
    affected_candidate_count = len(affected_candidates or [])

    # Policy signals must be conservative. Events that refer to pages absent from
    # the latest answer, or that use an explicit query that differs from the latest
    # ask, should enter review first instead of immediately changing ranking.
    policy_signal_eligible = True
    if allow_unvalidated_policy_signal:
        policy_signal_eligible = True
        warnings.append("unvalidated_policy_signal_override")
    else:
        if not query_fingerprint_matches_latest:
            policy_signal_eligible = False
        if affected_not_in_answer or expected_not_in_answer:
            policy_signal_eligible = False
        if not context.get("grouped_results_present"):
            policy_signal_eligible = False

    context_status = "valid" if policy_signal_eligible else "needs_review"
    return {
        "context_status": context_status,
        "policy_signal_eligible": bool(policy_signal_eligible),
        "query_fingerprint_matches_latest": bool(query_fingerprint_matches_latest),
        "latest_query_fingerprint": latest_qfp,
        "explicit_context_supplied": bool(explicit_context_supplied),
        "affected_pages_in_answer": sorted(affected_set & grouped_pages),
        "expected_pages_in_answer": sorted(expected_set & grouped_pages),
        "affected_pages_not_in_answer": affected_not_in_answer,
        "expected_pages_not_in_answer": expected_not_in_answer,
        "affected_candidate_count": affected_candidate_count,
        "grouped_page_count": len(grouped_pages),
        "warnings": sorted(dict.fromkeys(warnings)),
    }


@dataclass
class FeedbackOptions:
    rating: str
    reason_codes: Sequence[str]
    comment: str = ""
    affected_page_ids: Sequence[str] = ()
    expected_page_ids: Sequence[str] = ()
    affected_candidate_ids: Sequence[str] = ()
    query: str = ""
    part_number: str = ""
    page_id: str = ""
    reviewer: str = ""
    review_status: str = "pending"
    open_review: bool = False
    allow_unvalidated_policy_signal: bool = False


def make_feedback_event(paths: FeedbackPaths, options: FeedbackOptions) -> Dict[str, Any]:
    context = _infer_latest_context(paths)
    rating = _normalize_rating(options.rating)
    reasons = _normalize_reason_codes(options.reason_codes)
    affected_pages = _normalize_page_ids(options.affected_page_ids)
    expected_pages = _normalize_page_ids(options.expected_page_ids)
    affected_candidates = _normalize_candidate_ids(options.affected_candidate_ids)

    explicit_context_supplied = bool(options.query or options.part_number or options.page_id)
    query = options.query.strip() if options.query else context.get("query", "")
    part_number = options.part_number.strip() if options.part_number else context.get("part_number", "")
    page_id = options.page_id.strip() if options.page_id else context.get("page_id", "")
    query_fingerprint = _query_fingerprint(query, part_number, page_id)

    validation = _validate_feedback_context(
        context=context,
        query_fingerprint=query_fingerprint,
        affected_pages=affected_pages,
        expected_pages=expected_pages,
        affected_candidates=affected_candidates,
        explicit_context_supplied=explicit_context_supplied,
        allow_unvalidated_policy_signal=options.allow_unvalidated_policy_signal,
    )

    created_at = _utc_now()
    event_seed = json.dumps(
        {
            "created_at": created_at,
            "rating": rating,
            "query": query,
            "reasons": reasons,
            "affected_pages": affected_pages,
            "expected_pages": expected_pages,
            "comment": options.comment,
            "uuid": str(uuid.uuid4()),
        },
        sort_keys=True,
    )
    feedback_id = "feedback:" + _sha1_text(event_seed, 16)

    event = {
        "feedback_id": feedback_id,
        "created_at": created_at,
        "schema_version": "trace_net_feedback_event_v1",
        "rating": rating,
        "reason_codes": reasons,
        "comment": options.comment or "",
        "reviewer": options.reviewer or "",
        "review_status": options.review_status or "pending",
        "query": query,
        "part_number": part_number,
        "page_id": page_id,
        "query_fingerprint": query_fingerprint,
        "ask_run_id": context.get("ask_run_id"),
        "answer_id": context.get("answer_id"),
        "affected_page_ids": affected_pages,
        "expected_page_ids": expected_pages,
        "affected_candidate_ids": affected_candidates,
        "latest_grouped_page_ids": context.get("grouped_page_ids", []),
        "answer_evidence_records": context.get("answer_evidence_records", 0),
        "context_validation": validation,
        "context_status": validation.get("context_status"),
        "policy_signal_eligible": validation.get("policy_signal_eligible"),
        "pipeline_versions": context.get("pipeline_versions", {}),
        "source_artifacts": context.get("source_artifacts", {}),
        "advisory_only": True,
        "source_truth_mutation": False,
        "ranking_mutation": False,
        "notes": [
            "Feedback is advisory and does not mutate source truth.",
            "Future ranking changes must pass a separate policy/quality gate.",
            "Feedback must pass context validation before it can generate ranking policy signals.",
        ],
    }
    return event


def record_feedback_event(paths: FeedbackPaths, options: FeedbackOptions) -> Dict[str, Any]:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    event = make_feedback_event(paths, options)
    _append_jsonl(paths.feedback_events, event)
    build = build_feedback_graph(paths)
    return {"event": event, "build": build}


def _node(node_id: str, label: str, node_type: str, **attrs: Any) -> Dict[str, Any]:
    data = {"id": node_id, "label": label, "type": node_type}
    data.update({k: v for k, v in attrs.items() if v is not None})
    return data


def _edge(source: str, target: str, edge_type: str, **attrs: Any) -> Dict[str, Any]:
    data = {"source": source, "target": target, "type": edge_type}
    data.update({k: v for k, v in attrs.items() if v is not None})
    return data


def _rating_score(rating: str) -> float:
    if rating == "thumbs_up":
        return 1.0
    if rating == "thumbs_down":
        return -1.0
    return 0.0


def _make_policy_signals(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    aggregate: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for event in events:
        if event.get("policy_signal_eligible") is not True:
            continue
        qfp = event.get("query_fingerprint") or _query_fingerprint(event.get("query", ""), event.get("part_number", ""), event.get("page_id", ""))
        score = _rating_score(event.get("rating", "neutral"))
        reasons = event.get("reason_codes") or []
        for page_id in event.get("affected_page_ids") or []:
            key = (qfp, page_id)
            item = aggregate.setdefault(
                key,
                {
                    "query_fingerprint": qfp,
                    "page_id": page_id,
                    "net_score": 0.0,
                    "positive_events": 0,
                    "negative_events": 0,
                    "neutral_events": 0,
                    "event_count": 0,
                    "reason_counts": Counter(),
                    "feedback_ids": [],
                },
            )
            item["net_score"] += score
            item["event_count"] += 1
            item["feedback_ids"].append(event.get("feedback_id"))
            item["reason_counts"].update(reasons)
            if score > 0:
                item["positive_events"] += 1
            elif score < 0:
                item["negative_events"] += 1
            else:
                item["neutral_events"] += 1
        # If a user supplies expected pages on a negative event, create a weak boost signal for those pages.
        if event.get("rating") == "thumbs_down":
            for page_id in event.get("expected_page_ids") or []:
                key = (qfp, page_id)
                item = aggregate.setdefault(
                    key,
                    {
                        "query_fingerprint": qfp,
                        "page_id": page_id,
                        "net_score": 0.0,
                        "positive_events": 0,
                        "negative_events": 0,
                        "neutral_events": 0,
                        "event_count": 0,
                        "reason_counts": Counter(),
                        "feedback_ids": [],
                    },
                )
                item["net_score"] += 0.5
                item["positive_events"] += 1
                item["event_count"] += 1
                item["feedback_ids"].append(event.get("feedback_id"))
                item["reason_counts"].update(["expected_page"])

    signals: List[Dict[str, Any]] = []
    for (qfp, page_id), item in sorted(aggregate.items()):
        net = float(item["net_score"])
        events = max(1, int(item["event_count"]))
        if net > 0:
            signal = "boost_for_query"
        elif net < 0:
            signal = "demote_for_query"
        else:
            signal = "review_for_query"
        reason_counts = dict(item["reason_counts"])
        if any(reason in reason_counts for reason in ["wrong_page", "citation_not_supporting_answer", "wrong_part", "table_data_wrong"]):
            requires_review = True
        else:
            requires_review = signal != "boost_for_query"
        signals.append(
            {
                "signal_id": "feedback_signal:" + _sha1_text(f"{qfp}|{page_id}"),
                "query_fingerprint": qfp,
                "page_id": page_id,
                "signal": signal,
                "strength": round(min(1.0, abs(net) / events), 6),
                "net_score": round(net, 6),
                "event_count": events,
                "positive_events": item["positive_events"],
                "negative_events": item["negative_events"],
                "neutral_events": item["neutral_events"],
                "reason_counts": reason_counts,
                "feedback_ids": sorted(fid for fid in item["feedback_ids"] if fid),
                "requires_review": requires_review,
                "advisory_only": True,
                "ranking_mutation": False,
            }
        )
    return signals


def _render_review(summary: Dict[str, Any], events: List[Dict[str, Any]], signals: List[Dict[str, Any]]) -> Tuple[str, str]:
    lines: List[str] = []
    lines.append("# TRACE-Net Feedback Graph v1")
    lines.append("")
    lines.append(f"Status: **{summary.get('status')}**")
    lines.append("")
    lines.append("## Summary")
    for key in [
        "feedback_events",
        "thumbs_up_events",
        "thumbs_down_events",
        "neutral_events",
        "affected_page_count",
        "affected_candidate_count",
        "policy_signal_records",
        "policy_signal_eligible_events",
        "context_valid_events",
        "context_warning_events",
        "query_mismatch_events",
        "affected_page_not_in_answer_events",
        "advisory_only_events",
        "source_truth_mutation_records",
    ]:
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.append("")
    lines.append("## Recent feedback events")
    if not events:
        lines.append("")
        lines.append("No feedback events recorded yet.")
    else:
        lines.append("")
        lines.append("| Created | Rating | Context | Query | Affected pages | Reasons | Comment |")
        lines.append("|---|---|---|---|---|---|---|")
        for event in events[-25:]:
            lines.append(
                "| {created} | {rating} | {context} | `{query}` | {pages} | {reasons} | {comment} |".format(
                    created=html.escape(str(event.get("created_at", ""))),
                    rating=html.escape(str(event.get("rating", ""))),
                    context=html.escape(str(event.get("context_status", "unknown"))),
                    query=html.escape(str(event.get("query") or event.get("query_fingerprint") or "")),
                    pages=html.escape(", ".join(event.get("affected_page_ids") or []) or "-"),
                    reasons=html.escape(", ".join(event.get("reason_codes") or []) or "-"),
                    comment=html.escape(str(event.get("comment", "")))[:300],
                )
            )
    lines.append("")
    lines.append("## Advisory policy signals")
    if not signals:
        lines.append("")
        lines.append("No policy signals generated yet.")
    else:
        lines.append("")
        lines.append("| Signal | Query fingerprint | Page | Strength | Events | Reasons |")
        lines.append("|---|---|---|---:|---:|---|")
        for signal in signals[:50]:
            reasons = ", ".join(f"{k}:{v}" for k, v in sorted((signal.get("reason_counts") or {}).items()))
            lines.append(
                "| {sig} | `{q}` | {page} | {strength} | {events} | {reasons} |".format(
                    sig=html.escape(str(signal.get("signal", ""))),
                    q=html.escape(str(signal.get("query_fingerprint", ""))),
                    page=html.escape(str(signal.get("page_id", ""))),
                    strength=signal.get("strength", 0),
                    events=signal.get("event_count", 0),
                    reasons=html.escape(reasons or "-"),
                )
            )
    md = "\n".join(lines) + "\n"
    body = "\n".join(f"<p>{html.escape(line)}</p>" if line and not line.startswith("|") and not line.startswith("#") else f"<pre>{html.escape(line)}</pre>" for line in lines)
    doc = "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Feedback Graph</title>"
    doc += "<style>body{font-family:Arial,sans-serif;margin:24px;line-height:1.4}pre{background:#f6f8fa;padding:4px;white-space:pre-wrap}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:4px}</style>"
    doc += "</head><body>" + body + "</body></html>"
    return md, doc


def build_feedback_graph(paths: FeedbackPaths) -> Dict[str, Any]:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    events = _read_jsonl(paths.feedback_events)
    signals = _make_policy_signals(events)

    node_map: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    def add_node(record: Dict[str, Any]) -> None:
        node_map.setdefault(record["id"], record)

    add_node(_node("feedback_graph", "TRACE-Net Feedback Graph", "FeedbackGraph"))

    rating_counts = Counter()
    reason_counts: Counter[str] = Counter()
    affected_pages: set[str] = set()
    expected_pages: set[str] = set()
    affected_candidates: set[str] = set()
    advisory_only_count = 0
    mutation_count = 0
    ask_linked_count = 0
    answer_linked_count = 0
    context_valid_count = 0
    context_warning_count = 0
    policy_signal_eligible_count = 0
    query_mismatch_count = 0
    affected_page_not_in_answer_count = 0
    expected_page_not_in_answer_count = 0
    validation_warning_counts: Counter[str] = Counter()

    for event in events:
        feedback_id = event.get("feedback_id") or "feedback:" + _sha1_text(json.dumps(event, sort_keys=True))
        rating = event.get("rating", "neutral")
        rating_counts[rating] += 1
        if event.get("advisory_only") is True:
            advisory_only_count += 1
        if event.get("source_truth_mutation") or event.get("ranking_mutation"):
            mutation_count += 1
        validation = event.get("context_validation") or {}
        warnings = validation.get("warnings") or []
        validation_warning_counts.update(warnings)
        if event.get("context_status") == "valid":
            context_valid_count += 1
        else:
            context_warning_count += 1
        if event.get("policy_signal_eligible") is True:
            policy_signal_eligible_count += 1
        if validation.get("query_fingerprint_matches_latest") is False:
            query_mismatch_count += 1
        if validation.get("affected_pages_not_in_answer"):
            affected_page_not_in_answer_count += 1
        if validation.get("expected_pages_not_in_answer"):
            expected_page_not_in_answer_count += 1

        add_node(
            _node(
                feedback_id,
                feedback_id,
                "FeedbackEvent",
                rating=rating,
                created_at=event.get("created_at"),
                query_fingerprint=event.get("query_fingerprint"),
                review_status=event.get("review_status"),
                advisory_only=event.get("advisory_only"),
                context_status=event.get("context_status"),
                policy_signal_eligible=event.get("policy_signal_eligible"),
                validation_warnings=warnings,
            )
        )
        edges.append(_edge("feedback_graph", feedback_id, "HAS_FEEDBACK_EVENT"))

        status_node = "context_status:" + str(event.get("context_status", "unknown"))
        add_node(_node(status_node, str(event.get("context_status", "unknown")), "FeedbackContextStatus"))
        edges.append(_edge(feedback_id, status_node, "HAS_CONTEXT_STATUS"))
        for warning in warnings:
            warning_node = "context_warning:" + str(warning)
            add_node(_node(warning_node, str(warning), "FeedbackContextWarning"))
            edges.append(_edge(feedback_id, warning_node, "HAS_CONTEXT_WARNING"))

        qfp = event.get("query_fingerprint") or _query_fingerprint(event.get("query", ""), event.get("part_number", ""), event.get("page_id", ""))
        q_node = "query:" + _sha1_text(qfp, 16)
        add_node(_node(q_node, qfp, "QueryFingerprint", query_fingerprint=qfp))
        edges.append(_edge(feedback_id, q_node, "HAS_QUERY_FINGERPRINT"))

        rating_node = "rating:" + rating
        add_node(_node(rating_node, rating, "FeedbackRating"))
        edges.append(_edge(feedback_id, rating_node, "HAS_RATING"))

        ask_run = event.get("ask_run_id")
        if ask_run:
            ask_linked_count += 1
            ask_node = "ask_run:" + _sha1_text(str(ask_run), 16)
            add_node(_node(ask_node, str(ask_run), "AskRun"))
            edges.append(_edge(feedback_id, ask_node, "FEEDBACK_ON_ASK_RUN"))

        answer_id = event.get("answer_id")
        if answer_id:
            answer_linked_count += 1
            answer_node = "answer:" + _sha1_text(str(answer_id), 16)
            add_node(_node(answer_node, str(answer_id), "AnswerDraft"))
            edges.append(_edge(feedback_id, answer_node, "FEEDBACK_ON_ANSWER"))

        for reason in event.get("reason_codes") or []:
            reason_counts[reason] += 1
            reason_node = "reason:" + reason
            add_node(_node(reason_node, reason, "FeedbackReason"))
            edges.append(_edge(feedback_id, reason_node, "HAS_REASON"))

        for page_id in event.get("affected_page_ids") or []:
            affected_pages.add(page_id)
            page_node = "page:" + page_id
            add_node(_node(page_node, page_id, "Page"))
            edges.append(_edge(feedback_id, page_node, "FLAGS_AFFECTED_PAGE"))

        for page_id in event.get("expected_page_ids") or []:
            expected_pages.add(page_id)
            page_node = "page:" + page_id
            add_node(_node(page_node, page_id, "Page"))
            edges.append(_edge(feedback_id, page_node, "EXPECTS_PAGE"))

        for candidate_id in event.get("affected_candidate_ids") or []:
            affected_candidates.add(candidate_id)
            candidate_node = "candidate:" + _sha1_text(candidate_id, 16)
            add_node(_node(candidate_node, candidate_id, "CandidateChunk"))
            edges.append(_edge(feedback_id, candidate_node, "FLAGS_CANDIDATE"))

    for signal in signals:
        signal_id = signal.get("signal_id")
        add_node(
            _node(
                signal_id,
                signal.get("signal", "feedback_signal"),
                "FeedbackPolicySignal",
                signal=signal.get("signal"),
                query_fingerprint=signal.get("query_fingerprint"),
                page_id=signal.get("page_id"),
                strength=signal.get("strength"),
                advisory_only=True,
            )
        )
        edges.append(_edge("feedback_graph", signal_id, "HAS_POLICY_SIGNAL"))
        page_id = signal.get("page_id")
        if page_id:
            page_node = "page:" + page_id
            add_node(_node(page_node, page_id, "Page"))
            edges.append(_edge(signal_id, page_node, "SIGNAL_FOR_PAGE"))

    nodes = list(node_map.values())
    summary = {
        "status": "OK",
        "version": "trace_net_feedback_graph_v1_1",
        "created_at": _utc_now(),
        "feedback_events": len(events),
        "thumbs_up_events": rating_counts.get("thumbs_up", 0),
        "thumbs_down_events": rating_counts.get("thumbs_down", 0),
        "neutral_events": rating_counts.get("neutral", 0),
        "reason_counts": dict(reason_counts),
        "affected_page_count": len(affected_pages),
        "expected_page_count": len(expected_pages),
        "affected_candidate_count": len(affected_candidates),
        "ask_linked_event_records": ask_linked_count,
        "answer_linked_event_records": answer_linked_count,
        "context_valid_events": context_valid_count,
        "context_warning_events": context_warning_count,
        "policy_signal_eligible_events": policy_signal_eligible_count,
        "query_mismatch_events": query_mismatch_count,
        "affected_page_not_in_answer_events": affected_page_not_in_answer_count,
        "expected_page_not_in_answer_events": expected_page_not_in_answer_count,
        "context_validation_warning_counts": dict(validation_warning_counts),
        "advisory_only_events": advisory_only_count,
        "source_truth_mutation_records": mutation_count,
        "policy_signal_records": len(signals),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "events_path": str(paths.feedback_events),
        "signals_path": str(paths.policy_signals),
    }

    _write_json(paths.summary, summary)
    _write_json(paths.graph_nodes, nodes)
    _write_json(paths.graph_edges, edges)
    _write_jsonl(paths.policy_signals, signals)
    md, html_doc = _render_review(summary, events, signals)
    paths.review_md.write_text(md, encoding="utf-8")
    paths.review_html.write_text(html_doc, encoding="utf-8")
    return {"summary": summary, "nodes": nodes, "edges": edges, "signals": signals}


def _make_paths(args: argparse.Namespace) -> FeedbackPaths:
    trace_net_dir = Path(args.trace_net_dir) if getattr(args, "trace_net_dir", None) else TRACE_NET_DIR
    output_dir = Path(args.output_dir) if getattr(args, "output_dir", None) else trace_net_dir / "feedback"
    return FeedbackPaths(trace_net_dir=trace_net_dir, output_dir=output_dir)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record TRACE-Net answer/search feedback and build a feedback graph overlay.")
    parser.add_argument("--trace-net-dir", default=str(TRACE_NET_DIR))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--rating", required=True, help="thumbs_up, thumbs_down, or neutral")
    parser.add_argument("--reason-code", action="append", default=[], help="Reason code. May be repeated or comma-separated.")
    parser.add_argument("--comment", default="")
    parser.add_argument("--affected-page-id", action="append", default=[], help="Affected page ID. May be repeated or comma-separated.")
    parser.add_argument("--expected-page-id", action="append", default=[], help="Expected page ID. May be repeated or comma-separated.")
    parser.add_argument("--affected-candidate-id", action="append", default=[], help="Affected candidate/chunk ID. May be repeated or comma-separated.")
    parser.add_argument("--query", default="")
    parser.add_argument("--part-number", default="")
    parser.add_argument("--page-id", default="")
    parser.add_argument("--allow-unvalidated-policy-signal", action="store_true", help="Unsafe/debug: allow policy signals even when feedback context does not validate.")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--review-status", default="pending")
    parser.add_argument("--open", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    paths = _make_paths(args)
    options = FeedbackOptions(
        rating=args.rating,
        reason_codes=args.reason_code,
        comment=args.comment,
        affected_page_ids=args.affected_page_id,
        expected_page_ids=args.expected_page_id,
        affected_candidate_ids=args.affected_candidate_id,
        query=args.query,
        part_number=args.part_number,
        page_id=args.page_id,
        reviewer=args.reviewer,
        review_status=args.review_status,
        open_review=args.open,
        allow_unvalidated_policy_signal=args.allow_unvalidated_policy_signal,
    )
    result = record_feedback_event(paths, options)
    event = result["event"]
    summary = result["build"]["summary"]

    print("TRACE-Net feedback recorder")
    print(f"  Status: {summary['status']}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Event:")
    print(f"    feedback_id: {event['feedback_id']}")
    print(f"    rating: {event['rating']}")
    print(f"    query_fingerprint: {event['query_fingerprint']}")
    print(f"    affected_pages: {', '.join(event.get('affected_page_ids') or []) or '-'}")
    print(f"    reasons: {', '.join(event.get('reason_codes') or []) or '-'}")
    print(f"    context_status: {event.get('context_status')}")
    print(f"    policy_signal_eligible: {event.get('policy_signal_eligible')}")
    print("  Summary:")
    for key in ["feedback_events", "thumbs_up_events", "thumbs_down_events", "neutral_events", "context_valid_events", "context_warning_events", "policy_signal_eligible_events", "policy_signal_records", "source_truth_mutation_records", "graph_nodes", "graph_edges"]:
        print(f"    {key}: {summary.get(key)}")
    print("Files written:")
    print(f"  events: {paths.feedback_events}")
    print(f"  summary: {paths.summary}")
    print(f"  policy_signals: {paths.policy_signals}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")
    print(f"  review_html: {paths.review_html}")
    if args.open:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
