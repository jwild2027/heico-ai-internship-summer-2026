from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/build_trace_net_visual_question_context_gate_v1.py")


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in records) + "\n",
        encoding="utf-8",
    )


def test_visual_question_context_gate_splits_confirmed_review_and_excluded(tmp_path: Path) -> None:
    contexts = tmp_path / "visual_context.jsonl"
    detector = tmp_path / "detector.jsonl"
    out = tmp_path / "out"

    write_jsonl(
        contexts,
        [
            {"page_id": "p1", "visual_summary": {"text": "diagram"}},
            {"page_id": "p2", "visual_summary": {"text": "candidate"}},
            {"page_id": "p3", "visual_summary": {"text": "table"}},
        ],
    )
    write_jsonl(
        detector,
        [
            {
                "page_id": "p1",
                "module": "trace_net_meaningful_image_route_detector_v1_2",
                "new_route": "image_visual",
                "visual_subtype": "confirmed_diagram_dominant",
                "meaningful_image_visual": True,
                "route_confidence": 0.8,
            },
            {
                "page_id": "p2",
                "module": "trace_net_meaningful_image_route_detector_v1_2",
                "new_route": "visual_candidate_review",
                "visual_subtype": "visual_candidate_review",
                "meaningful_image_visual": False,
                "route_confidence": 0.5,
            },
            {
                "page_id": "p3",
                "module": "trace_net_meaningful_image_route_detector_v1_2",
                "new_route": "table",
                "visual_subtype": "table_dominant",
                "meaningful_image_visual": False,
                "route_confidence": 0.7,
            },
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--visual-context-jsonl",
            str(contexts),
            "--meaningful-image-detector-jsonl",
            str(detector),
            "--output-dir",
            str(out),
            "--min-source-contexts",
            "3",
            "--min-confirmed-contexts",
            "1",
            "--max-missing-detector-records",
            "0",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["quality_status"] == "PASS"
    assert summary["summary"]["source_context_count"] == 3
    assert summary["summary"]["confirmed_image_context_count"] == 1
    assert summary["summary"]["visual_candidate_review_context_count"] == 1
    assert summary["summary"]["excluded_context_count"] == 1
    assert summary["summary"]["missing_detector_record_count"] == 0
    assert summary["summary"]["final_answer_allowed_true_count"] == 0
    assert summary["summary"]["source_truth_mutation_allowed_count"] == 0

    confirmed = [
        json.loads(x)
        for x in (out / "trace_net_visual_question_context_gate_v1_confirmed_image_context.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x.strip()
    ]
    assert confirmed[0]["page_id"] == "p1"
    assert confirmed[0]["meaningful_image_gate"]["gate_status"] == "confirmed_image_context"
    assert confirmed[0]["final_answer_allowed"] is False


def test_visual_question_context_gate_fails_on_missing_detector_when_threshold_zero(tmp_path: Path) -> None:
    contexts = tmp_path / "visual_context.jsonl"
    detector = tmp_path / "detector.jsonl"
    out = tmp_path / "out"

    write_jsonl(contexts, [{"page_id": "p1"}])
    write_jsonl(detector, [])

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--visual-context-jsonl",
            str(contexts),
            "--meaningful-image-detector-jsonl",
            str(detector),
            "--output-dir",
            str(out),
            "--min-source-contexts",
            "1",
            "--min-confirmed-contexts",
            "0",
            "--max-missing-detector-records",
            "0",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["quality_status"] == "FAIL"
    assert summary["summary"]["missing_detector_record_count"] == 1
