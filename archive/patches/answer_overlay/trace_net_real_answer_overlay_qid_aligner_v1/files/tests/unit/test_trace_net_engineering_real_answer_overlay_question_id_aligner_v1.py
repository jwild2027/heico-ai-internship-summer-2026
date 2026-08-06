from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_engineering_real_answer_overlay_question_id_aligner_v1 import (
    OUTPUT_NAME,
    build_question_id_aligned_overlay_map,
)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_aligner_keys_overlay_to_real_answer_question_id(tmp_path: Path) -> None:
    source_answer = tmp_path / "real_answer.json"
    source_overlay = tmp_path / "overlay.json"
    out_dir = tmp_path / "out"

    _write(
        source_answer,
        {
            "quality_status": "PASS",
            "records": [
                {
                    "question_id": "q01",
                    "question": "What does figure 69 show?",
                    "answer_permission": False,
                }
            ],
        },
    )
    _write(
        source_overlay,
        {
            "quality_status": "PASS",
            "records": [
                {
                    "question_id": "old_query_id",
                    "question": "Looking for eligibility documents for PN DF250040-501",
                    "engram_overlay_text": "Existing eligibility guidance only; not proof.",
                    "answer_permission": False,
                }
            ],
        },
    )

    result = build_question_id_aligned_overlay_map(
        source_answer_smoke=source_answer,
        source_overlay_map=source_overlay,
        output_dir=out_dir,
        min_records=1,
        min_matched_question_ids=1,
        require_no_answer_permission=True,
        max_write_attempts=0,
    )

    assert result["quality_status"] == "PASS"
    assert result["summary"]["aligned_overlay_record_count"] == 1
    assert result["summary"]["matched_question_id_count"] == 1
    assert result["summary"]["answer_permission_count"] == 0
    assert (out_dir / OUTPUT_NAME).exists()

    record = result["records"][0]
    assert record["question_id"] == "q01"
    assert record["query_id"] == "q01"
    assert record["matched_real_answer_question_id"] is True
    assert record["answer_permission"] is False
    assert record["source_truth_mutation_allowed"] is False
    assert record["proof_role"] == "guidance_only"
    assert "QUESTION-ID ALIGNED" in record["engram_overlay_text"]
    assert "not proof" in record["engram_overlay_text"].lower()


def test_aligner_copies_same_question_text_overlay_safely(tmp_path: Path) -> None:
    source_answer = tmp_path / "real_answer.json"
    source_overlay = tmp_path / "overlay.json"
    out_dir = tmp_path / "out"

    question = "What does figure 69 show?"
    _write(source_answer, {"records": [{"question_id": "q01", "question": question}]})
    _write(
        source_overlay,
        {
            "records": [
                {
                    "question_id": "different_id",
                    "question": question,
                    "overlay_text": "Figure questions require visual proof_context citations only.",
                    "answer_permission": False,
                }
            ]
        },
    )

    result = build_question_id_aligned_overlay_map(
        source_answer_smoke=source_answer,
        source_overlay_map=source_overlay,
        output_dir=out_dir,
        min_records=1,
        min_matched_question_ids=1,
    )

    record = result["records"][0]
    assert record["question_id"] == "q01"
    assert record["matched_source_overlay"] is True
    assert record["source_overlay_match_reason"] == "source_overlay_same_question_text"
    assert "Figure questions require visual proof_context citations only." in record["engram_overlay_text"]


def test_aligner_fails_when_no_records(tmp_path: Path) -> None:
    source_answer = tmp_path / "real_answer.json"
    source_overlay = tmp_path / "overlay.json"
    out_dir = tmp_path / "out"

    _write(source_answer, {"records": []})
    _write(source_overlay, {"records": []})

    result = build_question_id_aligned_overlay_map(
        source_answer_smoke=source_answer,
        source_overlay_map=source_overlay,
        output_dir=out_dir,
        min_records=1,
        min_matched_question_ids=1,
    )

    assert result["quality_status"] == "FAIL"
    assert result["summary"]["quality_failures"]
