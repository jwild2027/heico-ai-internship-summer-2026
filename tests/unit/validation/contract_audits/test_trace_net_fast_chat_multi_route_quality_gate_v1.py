from pathlib import Path
import json

from tiff.trace_net_fast_chat_multi_route_quality_gate_v1 import (
    build_fast_chat_multi_route_quality_gate,
)


def _write_report(path: Path, *, query_type: str, summary_overrides=None, answer="Answer cites [E1]."):
    summary = {
        "query_type": query_type,
        "query_route": {
            "exact_part_number": "fast_exact_part_answer",
            "figure_or_item": "fast_figure_item_answer",
            "part_family": "fast_part_family_answer",
            "plain_text": "planned_plain_text_context",
        }.get(query_type, "planned_plain_text_context"),
        "implemented_query_type": query_type in {"exact_part_number", "figure_or_item", "part_family"},
        "source_context_quality_status": "PASS",
        "fast_chat_runner_ready": query_type in {"exact_part_number", "figure_or_item", "part_family"},
        "answer_quality_gate_passed": query_type == "exact_part_number",
        "valid_answer_citation_count": 1,
        "invalid_answer_citation_count": 0,
        "violation_record_count": 0,
        "human_review_required_count": 0,
        "manual_review_required_count": 0,
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": 0,
    }
    if query_type == "exact_part_number":
        summary.update({"direct_exact_answer_record_count": 8, "query_part_number_count": 1})
    if query_type == "figure_or_item":
        summary.update({"figure_item_fast_answer_ready": True, "figure_item_answer_record_count": 1, "figure_item_answer_page_count": 1})
    if query_type == "part_family":
        summary.update({"part_family_fast_answer_ready": True, "part_family_answer_record_count": 3, "part_family_part_number_count": 3})
    if query_type == "plain_text":
        summary.update({"implemented_query_type": False, "fast_chat_runner_ready": False})
    if summary_overrides:
        summary.update(summary_overrides)
    payload = {"quality_status": "PASS", "summary": summary, "answer_text": answer}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_exact_part_route_passes(tmp_path: Path):
    report = _write_report(tmp_path / "fast.json", query_type="exact_part_number", answer="Part 120 found [E1].")
    out = build_fast_chat_multi_route_quality_gate(fast_chat_report=report, output_dir=tmp_path / "out")
    assert out["quality_status"] == "PASS"
    assert out["summary"]["webui_answer_ready"] is True
    assert out["summary"]["query_type"] == "exact_part_number"


def test_figure_item_route_passes_without_exact_answer_gate(tmp_path: Path):
    report = _write_report(tmp_path / "fast.json", query_type="figure_or_item", answer="Figure 85 item 1 is listed [E7].")
    out = build_fast_chat_multi_route_quality_gate(fast_chat_report=report, output_dir=tmp_path / "out")
    assert out["quality_status"] == "PASS"
    assert out["summary"]["webui_answer_ready"] is True
    assert out["summary"]["figure_item_answer_record_count"] == 1


def test_part_family_route_passes(tmp_path: Path):
    report = _write_report(tmp_path / "fast.json", query_type="part_family", answer="Family members include 120-1 and 120-2 [E1].")
    out = build_fast_chat_multi_route_quality_gate(fast_chat_report=report, output_dir=tmp_path / "out")
    assert out["quality_status"] == "PASS"
    assert out["summary"]["webui_answer_ready"] is True


def test_part_family_forbidden_word_fails(tmp_path: Path):
    report = _write_report(tmp_path / "fast.json", query_type="part_family", answer="Family members are interchangeable [E1].")
    out = build_fast_chat_multi_route_quality_gate(fast_chat_report=report, output_dir=tmp_path / "out")
    assert out["quality_status"] == "FAIL"
    assert any(v["code"] == "part_family_no_forbidden_equivalence_claim" for v in out["violations"])


def test_planned_route_safe_placeholder_passes_but_not_webui_ready(tmp_path: Path):
    report = _write_report(tmp_path / "fast.json", query_type="plain_text", answer="Planned route placeholder.")
    out = build_fast_chat_multi_route_quality_gate(fast_chat_report=report, output_dir=tmp_path / "out")
    assert out["quality_status"] == "PASS"
    assert out["summary"]["planned_route"] is True
    assert out["summary"]["webui_answer_ready"] is False
