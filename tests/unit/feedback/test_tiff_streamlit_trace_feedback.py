from __future__ import annotations

from tiff.streamlit_trace_feedback import (
    answer_quality_hint,
    compact_text,
    feedback_stats,
    find_first_ata,
    find_first_page_id,
    find_first_part,
    flatten_feedback_items,
    infer_trace_target,
    payload_summary,
    step_body,
    step_title,
    trace_steps,
)


def test_extract_common_trace_targets() -> None:
    assert find_first_part("What is 120-37313-001?") == "120-37313-001"
    assert find_first_page_id("trace t_p_120_1176_p000083 now") == "t_p_120_1176_p000083"
    assert find_first_ata("Find ATA 25-21-00") == "25-21-00"
    assert infer_trace_target("page t_p_120_1176_p000083", "120-37313-001")["type"] == "page"
    assert infer_trace_target("part 120-37313-001", "")["type"] == "part"
    assert infer_trace_target("Find evidence for 25-21-00", "")["type"] == "ata"


def test_payload_summary_reads_top_level_and_nested_summary() -> None:
    payload = {
        "status": "OK",
        "summary": {
            "part_number": "120-37313-001",
            "nomenclature": "HOLDER, MAGAZINE",
            "total_pages_found": 28,
        },
    }
    summary = payload_summary(payload)
    assert summary["status"] == "OK"
    assert summary["part_number"] == "120-37313-001"
    assert summary["nomenclature"] == "HOLDER, MAGAZINE"
    assert summary["total_pages_found"] == 28


def test_trace_steps_normalizes_strings_and_dicts() -> None:
    payload = {"trace": {"path": ["start", {"label": "Page", "target": "page:p1", "score": 0.9}]}}
    steps = trace_steps(payload)
    assert steps[0]["label"] == "start"
    assert steps[1]["label"] == "Page"
    assert "Page" in step_title(steps[1], 2)
    assert step_body(steps[1]) == {"score": 0.9}


def test_feedback_summary_helpers() -> None:
    payload = {
        "total": 2,
        "by_rating": {"up": 1, "down": 1},
        "by_category": {"useful": 1, "wrong_source": 1},
        "recent_feedback": [
            {"rating": "up", "category": "useful", "question": "Q1"},
            {"rating": "down", "category": "wrong_source", "question": "Q2"},
        ],
    }
    stats = feedback_stats(payload)
    assert stats["total"] == 2
    assert stats["rating:up"] == 1
    assert stats["category:wrong_source"] == 1
    assert len(flatten_feedback_items(payload)) == 2
    assert "source-trace" in answer_quality_hint("down", "wrong_source")


def test_compact_text_one_line() -> None:
    assert compact_text("hello\n   world", max_chars=100) == "hello world"
    assert compact_text("x" * 20, max_chars=10).endswith("…")
