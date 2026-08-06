from __future__ import annotations

from tiff.trace_net_answer_quality_guard_v1 import (
    duplicate_followup_count,
    evaluate_answer_quality,
)


FOLLOWUPS = [
    "What additional part number characters do you remember after the prefix 123?",
    "Do you know the manufacturer, vendor, or supplier?",
    "What component, function, or assembly is the part associated with?",
    "Do you know the ATA chapter or aircraft system?",
    "Do you remember a figure, diagram, IPL table, item number, or page?",
]


def render_once() -> str:
    return (
        "## Answer\n\n"
        "TRACE-Net found candidate evidence, not a final identification:\n"
        "- 1234567 — ATA 25-21-00; EMB CMM ATA 25-21-00 REV.4\n\n"
        "Candidate, visual, graph, summary, and semantic results are guidance only "
        "until resolved to direct source evidence.\n\n"
        "Helpful follow-up questions:\n"
        + "\n".join(f"- {question}" for question in FOLLOWUPS)
    )


def test_shared_words_across_distinct_followups_are_not_duplicates():
    answer = render_once()
    assert duplicate_followup_count(answer, FOLLOWUPS) == 0


def test_exact_repeated_question_is_detected():
    answer = render_once() + "\n- " + FOLLOWUPS[0]
    assert duplicate_followup_count(answer, FOLLOWUPS) == 1


def test_actual_guided_answer_shape_passes_duplicate_guard():
    failures = evaluate_answer_quality(
        query="I only know the part starts with 123",
        answer=render_once(),
        trace={
            "route": "guided_part_discovery",
            "follow_up_questions": FOLLOWUPS,
        },
    )
    assert not any(
        failure.startswith("duplicate_followup_topics:")
        for failure in failures
    ), failures
    assert "user_visible_noise_candidates:REV.4" not in failures


def test_duplicate_guard_still_fails_real_duplicate():
    failures = evaluate_answer_quality(
        query="I only know the part starts with 123",
        answer=render_once() + "\n- " + FOLLOWUPS[1],
        trace={
            "route": "guided_part_discovery",
            "follow_up_questions": FOLLOWUPS,
        },
    )
    assert "duplicate_followup_topics:1" in failures
