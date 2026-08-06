import json
from pathlib import Path

from tiff.trace_net_h33_full30_progress_runner_v1 import (
    build_h33_overlay_map,
    extract_overlay_map,
    format_progress_line,
    load_question_records,
)


def test_load_question_records_and_overlay(tmp_path):
    qb = tmp_path / "questions.jsonl"
    qb.write_text('\n'.join([
        json.dumps({"question_id": "q01", "question": "A?"}),
        json.dumps({"question_id": "q02", "question": "B?"}),
    ]) + '\n', encoding="utf-8")
    records = load_question_records(qb)
    assert [r["question_id"] for r in records] == ["q01", "q02"]
    manifest = build_h33_overlay_map(records, base_overlay_map={"q02": "BASE"})
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["overlay_map_record_count"] == 2
    assert "TRACE-NET H33 ANSWER BUDGET" in manifest["overlay_map"]["q01"]
    assert "BASE" in manifest["overlay_map"]["q02"]
    assert manifest["summary"]["answer_permission_count"] == 0


def test_extract_overlay_map_shapes():
    data = {
        "overlay_map": {"q01": "A"},
        "overlay_records": [{"question_id": "q02", "overlay_text": "B"}],
        "gate_records": [{"question_id": "q03", "overlay_text_preview": "C"}],
    }
    extracted = extract_overlay_map(data)
    assert extracted["q01"] == "A"
    assert extracted["q02"] == "B"
    assert extracted["q03"] == "C"


def test_progress_line_contains_count_and_qid():
    line = format_progress_line(completed=3, total=30, question_id="q03", answer_file="x_a.txt", elapsed_seconds=65)
    assert "3/30" in line
    assert "qid=q03" in line
    assert "file=x_a.txt" in line
    assert "elapsed=01:05" in line


def test_overlay_has_budget_and_citation_guard():
    manifest = build_h33_overlay_map([{"question_id": "q18"}], min_chars=400, target_max_chars=1200, hard_max_chars=1600)
    text = manifest["overlay_map"]["q18"]
    assert "Finish every answer completely" in text
    assert "Do not use grouped labels" in text
    assert "Manual/source claims still require current proof_context citations" in text
