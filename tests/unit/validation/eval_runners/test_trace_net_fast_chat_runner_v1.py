import json
from pathlib import Path

from tiff.trace_net_fast_chat_runner_v1 import build_fast_chat_runner, detect_query_type


def _context(tmp_path: Path) -> Path:
    records = [
        {
            "citation_label": "E1",
            "anchor_aware_role": "direct_exact_match_anchor",
            "proof_strength": "direct_exact_proof",
            "page_number": 361,
            "excerpt": "ASSY 85 - REF 1 | 120-29073-001 . STRUCTURE, LATERAL LEG VS4956 1 -2 | 120-29073-005 . STRUCTURE, LATERAL LEG 1 -3 | 120-29073-007 . STRUCTURE, LATERAL LEG",
        },
        {
            "citation_label": "E2",
            "anchor_aware_role": "family_variant_anchor",
            "proof_strength": "related_variant",
            "page_number": 32,
            "excerpt": "120-29073-005 120-29073-007",
        },
        {
            "citation_label": "E3",
            "anchor_aware_role": "same_anchor_leiden_community_neighbor",
            "proof_strength": "weak_candidate",
            "page_number": 55,
            "excerpt": "weak related context",
        },
    ]
    path = tmp_path / "context.json"
    path.write_text(json.dumps({"quality_status": "PASS", "summary": {"module": "test"}, "records": records}), encoding="utf-8")
    return path


def test_detect_exact_part_number():
    plan = detect_query_type("Find 120-29073-001")
    assert plan["query_type"] == "exact_part_number"
    assert plan["query_route"] == "fast_exact_part_answer"


def test_detect_figure_item():
    plan = detect_query_type("Show figure 85 item 1")
    assert plan["query_type"] == "figure_or_item"
    assert plan["figure"] == "85"
    assert plan["item"] == "1"


def test_detect_part_family():
    plan = detect_query_type("Show the 120-29073 family")
    assert plan["query_type"] == "part_family"
    assert plan["query_part_families"] == ["120-29073"]


def test_exact_runner_fallback_is_ready(tmp_path):
    context = _context(tmp_path)
    out = tmp_path / "exact"
    payload = build_fast_chat_runner(
        question="Find part number 120-29073-001",
        part_number="120-29073-001",
        context_pack=str(context),
        output_dir=str(out),
        run_multi_route_quality_gate=False,
        quality=False,
    )
    s = payload["summary"]
    assert payload["quality_status"] == "PASS"
    assert s["query_type"] == "exact_part_number"
    assert s["fast_chat_runner_ready"] is True
    assert s["webui_answer_ready"] is True
    assert (out / "trace_net_fast_chat_runner_v1_answer.md").exists()


def test_figure_item_runner_fallback_is_ready(tmp_path):
    context = _context(tmp_path)
    out = tmp_path / "fig"
    payload = build_fast_chat_runner(
        question="Show figure 85 item 1",
        context_pack=str(context),
        output_dir=str(out),
        run_multi_route_quality_gate=False,
        quality=False,
    )
    s = payload["summary"]
    assert s["query_type"] == "figure_or_item"
    assert s["figure_item_fast_answer_ready"] is True
    assert s["figure_item_answer_record_count"] == 1


def test_part_family_runner_fallback_is_ready(tmp_path):
    context = _context(tmp_path)
    out = tmp_path / "family"
    payload = build_fast_chat_runner(
        question="Show the 120-29073 family",
        context_pack=str(context),
        output_dir=str(out),
        run_multi_route_quality_gate=False,
        quality=False,
    )
    s = payload["summary"]
    assert s["query_type"] == "part_family"
    assert s["part_family_fast_answer_ready"] is True
    assert s["part_family_part_number_count"] >= 2
