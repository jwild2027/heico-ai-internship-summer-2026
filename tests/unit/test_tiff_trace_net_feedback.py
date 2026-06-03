from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_feedback import FeedbackOptions, FeedbackPaths, build_feedback_graph, record_feedback_event


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_context(trace: Path, query: str = "120-50645-009", grouped_pages=None):
    grouped_pages = grouped_pages or ["t_p_120_1176_p000003", "t_p_120_1176_p000320"]
    _write_json(trace / "ask" / "trace_net_ask_summary.json", {"version": "trace_net_ask_v1", "query": query, "part_number": query if query.startswith("120-") else ""})
    _write_json(trace / "answers" / "trace_net_answer_summary.json", {"version": "trace_net_answer_v1", "query": query, "answer_page_records": len(grouped_pages)})
    _write_json(trace / "search" / "trace_net_search_summary.json", {"version": "trace_net_search_v1", "effective_query": query, "part_number": query if query.startswith("120-") else ""})
    _write_jsonl(trace / "search" / "trace_net_search_grouped_results.jsonl", [{"page_id": p} for p in grouped_pages])


def test_record_feedback_event_flags_context_mismatch_when_page_not_in_answer(tmp_path: Path):
    trace = tmp_path / "trace_net"
    _write_context(trace, grouped_pages=["t_p_120_1176_p000003"])

    paths = FeedbackPaths(trace_net_dir=trace, output_dir=trace / "feedback")
    result = record_feedback_event(
        paths,
        FeedbackOptions(
            rating="thumbs_down",
            reason_codes=["wrong_page", "citation_not_supporting_answer"],
            affected_page_ids=["t_p_120_1176_p000320"],
            expected_page_ids=["t_p_120_1176_p000003"],
            comment="p000003 was better evidence.",
        ),
    )
    event = result["event"]
    assert event["rating"] == "thumbs_down"
    assert event["query_fingerprint"] == "part_number:120-50645-009"
    assert event["advisory_only"] is True
    assert event["source_truth_mutation"] is False
    assert event["context_status"] == "needs_review"
    assert event["policy_signal_eligible"] is False
    assert "affected_page_not_in_answer" in event["context_validation"]["warnings"]
    assert paths.feedback_events.exists()
    assert len(_read_jsonl(paths.feedback_events)) == 1
    assert _read_jsonl(paths.policy_signals) == []


def test_build_feedback_graph_generates_advisory_signals_for_valid_context(tmp_path: Path):
    trace = tmp_path / "trace_net"
    _write_context(trace, grouped_pages=["t_p_120_1176_p000003", "t_p_120_1176_p000320"])
    paths = FeedbackPaths(trace_net_dir=trace, output_dir=trace / "feedback")
    record_feedback_event(
        paths,
        FeedbackOptions(
            rating="thumbs_down",
            reason_codes=["wrong_page"],
            affected_page_ids=["t_p_120_1176_p000320"],
            expected_page_ids=["t_p_120_1176_p000003"],
        ),
    )
    build = build_feedback_graph(paths)
    summary = build["summary"]
    assert summary["feedback_events"] == 1
    assert summary["context_valid_events"] == 1
    assert summary["policy_signal_records"] == 2
    assert summary["source_truth_mutation_records"] == 0
    signals = _read_jsonl(paths.policy_signals)
    by_page = {s["page_id"]: s for s in signals}
    assert by_page["t_p_120_1176_p000320"]["signal"] == "demote_for_query"
    assert by_page["t_p_120_1176_p000003"]["signal"] == "boost_for_query"
    assert all(s["advisory_only"] for s in signals)


def test_neutral_feedback_records_review_signal_when_context_valid(tmp_path: Path):
    trace = tmp_path / "trace_net"
    _write_context(trace, query="seat bottom backrest", grouped_pages=["t_p_120_1176_p000015"])
    paths = FeedbackPaths(trace_net_dir=trace, output_dir=trace / "feedback")
    record_feedback_event(
        paths,
        FeedbackOptions(
            rating="neutral",
            reason_codes=["answer_too_vague"],
            affected_page_ids=["t_p_120_1176_p000015"],
        ),
    )
    signals = _read_jsonl(paths.policy_signals)
    assert len(signals) == 1
    assert signals[0]["signal"] == "review_for_query"
    assert signals[0]["requires_review"] is True


def test_explicit_context_different_from_latest_is_needs_review(tmp_path: Path):
    trace = tmp_path / "trace_net"
    _write_context(trace, query="seat bottom backrest", grouped_pages=["t_p_120_1176_p000015"])
    paths = FeedbackPaths(trace_net_dir=trace, output_dir=trace / "feedback")
    result = record_feedback_event(
        paths,
        FeedbackOptions(
            rating="thumbs_down",
            reason_codes=["wrong_page"],
            part_number="120-50645-009",
            affected_page_ids=["t_p_120_1176_p000320"],
            expected_page_ids=["t_p_120_1176_p000003"],
        ),
    )
    event = result["event"]
    assert event["query_fingerprint"] == "part_number:120-50645-009"
    assert event["context_status"] == "needs_review"
    assert event["policy_signal_eligible"] is False
    assert "explicit_query_context_differs_from_latest_ask" in event["context_validation"]["warnings"]
    assert _read_jsonl(paths.policy_signals) == []
