from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_feedback import FeedbackOptions, FeedbackPaths, build_feedback_graph, record_feedback_event
from tiff.trace_net_feedback_quality import FeedbackQualityPaths, check_feedback_quality


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _write_context(trace: Path):
    query = "seat bottom backrest"
    _write_json(trace / "ask" / "trace_net_ask_summary.json", {"version": "trace_net_ask_v1", "query": query})
    _write_json(trace / "answers" / "trace_net_answer_summary.json", {"version": "trace_net_answer_v1", "query": query, "answer_page_records": 1})
    _write_json(trace / "search" / "trace_net_search_summary.json", {"version": "trace_net_search_v1", "effective_query": query})
    _write_jsonl(trace / "search" / "trace_net_search_grouped_results.jsonl", [{"page_id": "t_p_120_1176_p000015"}])


def test_feedback_quality_passes_for_valid_advisory_event(tmp_path: Path):
    trace = tmp_path / "trace_net"
    _write_context(trace)
    paths = FeedbackPaths(trace_net_dir=trace, output_dir=trace / "feedback")
    record_feedback_event(
        paths,
        FeedbackOptions(
            rating="thumbs_up",
            reason_codes=["answer_correct"],
            affected_page_ids=["t_p_120_1176_p000015"],
        ),
    )
    qpaths = FeedbackQualityPaths(trace_net_dir=trace, feedback_dir=trace / "feedback", quality_path=trace / "feedback" / "quality.json")
    result = check_feedback_quality(
        qpaths,
        min_events=1,
        min_policy_signals=1,
        min_policy_signal_eligible_events=1,
        max_context_warning_events=0,
        max_source_truth_mutations=0,
    )
    assert result["status"] == "OK"
    assert result["feedback_events"] == 1
    assert result["feedback_context_valid_events"] == 1
    assert result["feedback_context_warning_events"] == 0
    assert result["feedback_source_truth_mutation_records"] == 0


def test_feedback_quality_flags_context_warning_when_requested(tmp_path: Path):
    trace = tmp_path / "trace_net"
    _write_context(trace)
    paths = FeedbackPaths(trace_net_dir=trace, output_dir=trace / "feedback")
    record_feedback_event(
        paths,
        FeedbackOptions(
            rating="thumbs_down",
            reason_codes=["wrong_page"],
            affected_page_ids=["t_p_120_1176_p000999"],
        ),
    )
    qpaths = FeedbackQualityPaths(trace_net_dir=trace, feedback_dir=trace / "feedback", quality_path=trace / "feedback" / "quality.json")
    result = check_feedback_quality(qpaths, min_events=1, max_context_warning_events=0)
    assert result["status"] == "FAIL"
    assert result["feedback_context_warning_events"] == 1
    assert any(c["name"] == "context_warning_events" and not c["ok"] for c in result["checks"])


def test_feedback_quality_fails_when_min_events_not_met(tmp_path: Path):
    trace = tmp_path / "trace_net"
    paths = FeedbackPaths(trace_net_dir=trace, output_dir=trace / "feedback")
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    build_feedback_graph(paths)
    qpaths = FeedbackQualityPaths(trace_net_dir=trace, feedback_dir=trace / "feedback", quality_path=trace / "feedback" / "quality.json")
    result = check_feedback_quality(qpaths, min_events=1)
    assert result["status"] == "FAIL"
    assert any(c["name"] == "feedback_events" and not c["ok"] for c in result["checks"])
