
import json
from pathlib import Path

from tiff.trace_net_engineering_question_orchestrator_v1 import (
    build_engineering_question_orchestrator,
    check_engineering_question_orchestrator_quality,
)


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _artifacts(tmp_path: Path, *, manual_ready=True):
    draft_text = "Source-backed facts: page_id p000001 shows evidence. " * 20
    draft_path = tmp_path / "draft_response.json"
    _write(draft_path, {"draft_text": draft_text, "raw_response": {"message": {"content": draft_text}}})
    runner = {
        "quality_status": "PASS",
        "records": [
            {
                "runner_record_id": "runner_1",
                "source_draft_packet_id": "draft_1",
                "draft_response_path": str(draft_path),
            }
        ],
    }
    gate = {
        "quality_status": "PASS",
        "records": [
            {
                "final_gate_record_id": "gate_1",
                "source_runner_record_id": "runner_1",
                "source_draft_packet_id": "draft_1",
                "user_question": "Find part number 120-29073-001 and nearby similar parts.",
                "intent_family": "exact_part_lookup",
                "model_id": "gemma4:26b",
                "final_gate_status": "FINAL_GATE_DRAFT_ACCEPTED_FOR_MANUAL_REVIEW" if manual_ready else "FINAL_GATE_BLOCKED",
                "ready_for_manual_review": manual_ready,
                "blocking_reasons": [] if manual_ready else ["draft_too_short"],
                "warning_reasons": [],
                "ready_for_final_answer": False,
                "answer_permission": False,
            }
        ],
    }
    return gate, runner, draft_text


def test_question_orchestrator_returns_manual_review_ready_draft(tmp_path):
    gate, runner, draft_text = _artifacts(tmp_path, manual_ready=True)
    gate_path = tmp_path / "gate.json"
    runner_path = tmp_path / "runner.json"
    _write(gate_path, gate)
    _write(runner_path, runner)

    payload = build_engineering_question_orchestrator(
        question="Find part number 120-29073-001 and nearby similar parts.",
        final_gate_report_path=gate_path,
        runner_report_path=runner_path,
        output_dir=tmp_path / "out",
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["matched_question_count"] == 1
    assert payload["summary"]["manual_review_ready_response_count"] == 1
    record = payload["records"][0]
    assert record["response_text"] == draft_text
    assert record["answer_permission"] is False
    assert record["ready_for_final_answer"] is False


def test_question_orchestrator_withholds_blocked_draft(tmp_path):
    gate, runner, _draft_text = _artifacts(tmp_path, manual_ready=False)
    gate_path = tmp_path / "gate.json"
    runner_path = tmp_path / "runner.json"
    _write(gate_path, gate)
    _write(runner_path, runner)

    payload = build_engineering_question_orchestrator(
        question="Find part number 120-29073-001 and nearby similar parts.",
        final_gate_report_path=gate_path,
        runner_report_path=runner_path,
        output_dir=tmp_path / "out",
    )

    record = payload["records"][0]
    assert record["controlled_response_status"] == "final_gate_blocked"
    assert record["response_text"] == ""
    assert payload["summary"]["manual_review_ready_response_count"] == 0


def test_quality_checker_passes(tmp_path):
    gate, runner, _draft_text = _artifacts(tmp_path, manual_ready=True)
    gate_path = tmp_path / "gate.json"
    runner_path = tmp_path / "runner.json"
    _write(gate_path, gate)
    _write(runner_path, runner)
    build_engineering_question_orchestrator(
        question="Find part number 120-29073-001",
        final_gate_report_path=gate_path,
        runner_report_path=runner_path,
        output_dir=tmp_path / "out",
    )
    report = tmp_path / "out" / "trace_net_engineering_question_orchestrator_v1.json"

    result = check_engineering_question_orchestrator_quality(
        report_path=report,
        require_source_final_gate_quality_pass=True,
        require_source_runner_quality_pass=True,
        min_matched_questions=1,
        min_manual_review_ready_responses=1,
        min_response_chars=300,
        max_ready_for_final_answer=0,
        require_no_answer_permission=True,
        require_no_llm_calls=True,
        require_no_retrieval_execution=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"
