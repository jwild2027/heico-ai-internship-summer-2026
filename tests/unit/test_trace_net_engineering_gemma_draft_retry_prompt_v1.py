
import json
from pathlib import Path

from tiff.trace_net_engineering_gemma_draft_retry_prompt_v1 import (
    build_engineering_gemma_draft_retry_prompt,
    check_engineering_gemma_draft_retry_prompt_quality,
)


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _final_gate_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "final_gate_record_id": "gate_1",
                "source_draft_packet_id": "draft_1",
                "source_runner_record_id": "runner_1",
                "question_id": "q1",
                "user_question": "Find part number 120-29073-001",
                "intent_family": "exact_part_lookup",
                "selected_playbook_id": "part_number_evidence_pack",
                "final_gate_status": "FINAL_GATE_BLOCKED",
                "blocking_reasons": ["draft_too_short"],
                "draft_preview": "###",
                "draft_text_char_count": 3,
            }
        ],
    }


def _draft_packet_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "draft_packet_id": "draft_1",
                "question_id": "q1",
                "user_question": "Find part number 120-29073-001",
                "intent_family": "exact_part_lookup",
                "selected_playbook_id": "part_number_evidence_pack",
                "prompt_contract": {
                    "user_question": "Find part number 120-29073-001",
                    "source_truth_evidence": [
                        {"route": "table", "trust_tier": "exact_source_evidence_candidate", "page_id": "p1", "excerpt": "120-29073-001 LATERAL STRUCTURE"},
                        {"route": "table", "trust_tier": "exact_source_evidence_candidate", "page_id": "p2", "excerpt": "120-29073-001 spare record"},
                        {"route": "normal_text", "trust_tier": "source_context_guidance", "page_id": "p3", "excerpt": "manual page context"},
                        {"route": "table", "trust_tier": "exact_source_evidence_candidate", "page_id": "p4", "excerpt": "extra should be trimmed"},
                    ],
                    "candidate_evidence": [
                        {"route": "graph", "trust_tier": "relationship_candidate", "page_id": "p5", "excerpt": "same assembly neighbor"},
                        {"route": "graph", "trust_tier": "relationship_candidate", "page_id": "p6", "excerpt": "nearby part"},
                        {"route": "graph", "trust_tier": "relationship_candidate", "page_id": "p7", "excerpt": "extra should be trimmed"},
                    ],
                    "missing_evidence": [],
                    "forbidden_claims": ["approved replacement"],
                    "answer_format_contract": {"answer_mode": "exact_evidence_first_then_related_context"},
                },
            }
        ],
    }


def test_build_micro_retry_prompt_adapter_compatible(tmp_path):
    gate = tmp_path / "gate.json"
    packet = tmp_path / "packet.json"
    _write(gate, _final_gate_payload())
    _write(packet, _draft_packet_payload())

    payload = build_engineering_gemma_draft_retry_prompt(
        final_gate_report_path=gate,
        draft_packet_path=packet,
        output_dir=tmp_path / "out",
        provider="ollama",
        model_id="gemma4:26b",
        min_draft_chars=300,
        prompt_style="micro",
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["retry_prompt_record_count"] == 1
    assert payload["summary"]["request_payload_written_count"] == 1
    assert payload["summary"]["prompt_style_counts"] == {"micro": 1}
    assert payload["summary"]["total_message_character_count"] < 7000
    record = payload["records"][0]
    assert record["provider"] == "ollama"
    assert record["request_payload"]["think"] is False
    assert record["request_payload"]["model"] == "gemma4:26b"
    assert record["prompt_style"] == "micro"
    assert "draft_too_short" in record["previous_blocking_reasons"]
    assert Path(record["request_payload_path"]).exists()
    user_msg = record["request_payload"]["messages"][1]["content"]
    assert "Do not use ###" in user_msg
    assert "Compact TRACE-Net packet" not in user_msg
    assert "Source-backed facts:" in user_msg


def test_quality_checker_passes_micro_limits(tmp_path):
    gate = tmp_path / "gate.json"
    packet = tmp_path / "packet.json"
    _write(gate, _final_gate_payload())
    _write(packet, _draft_packet_payload())
    build_engineering_gemma_draft_retry_prompt(
        final_gate_report_path=gate,
        draft_packet_path=packet,
        output_dir=tmp_path / "out",
        prompt_style="micro",
    )
    report = tmp_path / "out" / "trace_net_engineering_gemma_draft_retry_prompt_v1.json"

    result = check_engineering_gemma_draft_retry_prompt_quality(
        report_path=report,
        require_source_final_gate_quality_pass=True,
        require_source_draft_packet_quality_pass=True,
        min_retry_prompt_records=1,
        min_request_payloads_written=1,
        max_request_sent=0,
        max_ready_for_final_answer=0,
        require_ollama_think_false=True,
        require_prompt_style="micro",
        max_total_message_chars=7000,
        require_no_answer_permission=True,
        require_no_llm_calls=True,
        require_no_retrieval_execution=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"
