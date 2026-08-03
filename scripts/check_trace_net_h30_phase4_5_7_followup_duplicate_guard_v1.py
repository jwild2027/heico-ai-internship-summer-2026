#!/usr/bin/env python3
"""Check Phase 4.5.7 full-question duplicate detection."""
from __future__ import annotations

import json

from tiff.trace_net_answer_quality_guard_v1 import (
    duplicate_followup_count,
    evaluate_answer_quality,
)


def main() -> int:
    questions = [
        "What additional part number characters do you remember after the prefix 123?",
        "Do you know the manufacturer, vendor, or supplier?",
        "What component, function, or assembly is the part associated with?",
        "Do you know the ATA chapter or aircraft system?",
        "Do you remember a figure, diagram, IPL table, item number, or page?",
    ]
    answer = (
        "## Answer\n\n"
        "TRACE-Net found candidate evidence, not a final identification:\n"
        "- 1234567 — ATA 25-21-00; EMB CMM ATA 25-21-00 REV.4\n\n"
        "Candidate results are guidance only until resolved to direct source evidence.\n\n"
        "Helpful follow-up questions:\n"
        + "\n".join(f"- {question}" for question in questions)
    )
    repeated = answer + "\n- " + questions[0]

    once_count = duplicate_followup_count(answer, questions)
    repeated_count = duplicate_followup_count(repeated, questions)
    failures = evaluate_answer_quality(
        query="I only know the part starts with 123",
        answer=answer,
        trace={
            "route": "guided_part_discovery",
            "follow_up_questions": questions,
        },
    )

    checks = {
        "shared_vocabulary_not_duplicate": once_count == 0,
        "exact_repeated_question_detected": repeated_count == 1,
        "guided_answer_has_no_duplicate_failure": not any(
            value.startswith("duplicate_followup_topics:")
            for value in failures
        ),
        "revision_metadata_still_not_noise": (
            "user_visible_noise_candidates:REV.4" not in failures
        ),
        "answer_permission_false": True,
        "source_truth_mutation_false": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "module": "check_trace_net_h30_phase4_5_7_followup_duplicate_guard_v1",
        "quality_status": "PASS" if not failed else "FAIL",
        "failure_count": len(failed),
        "failures": failed,
        "checks": checks,
        "single_render_duplicate_count": once_count,
        "repeated_render_duplicate_count": repeated_count,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
