
import json
from pathlib import Path

from tiff.trace_net_engineering_draft_final_gate_v1 import (
    build_engineering_draft_final_gate,
    check_engineering_draft_final_gate_quality,
)


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _runner_payload(tmp_path: Path, draft_text: str):
    draft_path = tmp_path / "draft_response.json"
    _write(draft_path, {
        "draft_text": draft_text,
        "raw_response": {"message": {"content": draft_text}},
        "error": None,
        "draft_safety_scan": {},
    })
    return {
        "quality_status": "PASS",
        "records": [
            {
                "runner_record_id": "runner_1",
                "source_adapter_record_id": "adapter_1",
                "source_draft_packet_id": "draft_1",
                "question_id": "q1",
                "user_question": "Find part number 120-29073-001",
                "intent_family": "exact_part_lookup",
                "selected_playbook_id": "part_number_evidence_pack",
                "model_id": "gemma4:26b",
                "provider": "ollama",
                "response_received": True,
                "request_error": None,
                "ready_for_final_gate_review": len(draft_text) >= 1,
                "draft_response_path": str(draft_path),
            }
        ],
    }


def test_final_gate_allows_negated_do_not_claim_boundary(tmp_path):
    runner = tmp_path / "runner.json"
    draft = (
        "Source-backed facts: page_id p000001 shows the part in a table. "
        "Related candidate context: graph evidence is candidate context only. "
        "Missing evidence and review boundaries: no approval or interchangeability evidence is proven. "
        "Source trace notes: page_id p000001 is the source trace used here. "
        "Do-not-claim boundary: This draft does not claim that any part is an approved replacement or a guaranteed fit. "
        "No engineering approval or safety for installation is implied by this information. "
        "There are no claims regarding unverified synonyms or unproven alternate parts. "
    )
    _write(runner, _runner_payload(tmp_path, draft))

    payload = build_engineering_draft_final_gate(
        runner_report_path=runner,
        output_dir=tmp_path / "out",
        min_draft_chars=300,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["manual_review_ready_count"] == 1
    assert payload["summary"]["blocked_record_count"] == 0
    assert payload["summary"]["blocked_risky_phrase_hit_count"] == 0
    assert payload["summary"]["negated_risky_phrase_hit_count"] >= 2
    record = payload["records"][0]
    assert record["final_gate_status"] == "FINAL_GATE_DRAFT_ACCEPTED_FOR_MANUAL_REVIEW"
    assert record["ready_for_final_answer"] is False
    assert record["answer_permission"] is False


def test_final_gate_blocks_asserted_risky_claim(tmp_path):
    runner = tmp_path / "runner.json"
    draft = (
        "Source-backed facts: page_id p000001 shows the part in a table. "
        "Related candidate context: graph evidence is candidate context only. "
        "Missing evidence and review boundaries: details require review. "
        "Source trace notes: page_id p000001. "
        "Do-not-claim boundary: This is an approved replacement and a guaranteed fit for installation. "
    ) * 2
    _write(runner, _runner_payload(tmp_path, draft))

    payload = build_engineering_draft_final_gate(
        runner_report_path=runner,
        output_dir=tmp_path / "out",
        min_draft_chars=300,
    )

    assert payload["summary"]["blocked_record_count"] == 1
    assert payload["summary"]["blocked_risky_phrase_hit_count"] >= 1
    record = payload["records"][0]
    assert "risky_or_forbidden_claim_phrase_detected" in record["blocking_reasons"]


def test_quality_checker_passes_for_negated_manual_review_ready(tmp_path):
    runner = tmp_path / "runner.json"
    draft = (
        "Source-backed facts: page_id p000001 shows the part in a table. "
        "Related candidate context: graph evidence is candidate context only. "
        "Missing evidence and review boundaries: no approval evidence is proven. "
        "Source trace notes: page_id p000001. "
        "Do-not-claim boundary: This draft does not claim approved replacement or guaranteed fit. "
    ) * 2
    _write(runner, _runner_payload(tmp_path, draft))
    build_engineering_draft_final_gate(
        runner_report_path=runner,
        output_dir=tmp_path / "out",
        min_draft_chars=300,
    )
    report = tmp_path / "out" / "trace_net_engineering_draft_final_gate_v1.json"

    result = check_engineering_draft_final_gate_quality(
        report_path=report,
        require_source_runner_quality_pass=True,
        min_final_gate_records=1,
        min_manual_review_ready=1,
        max_blocked_risky_phrase_hits=0,
        min_negated_risky_phrase_hits=1,
        max_ready_for_final_answer=0,
        require_no_answer_permission=True,
        require_no_llm_calls=True,
        require_no_retrieval_execution=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"
