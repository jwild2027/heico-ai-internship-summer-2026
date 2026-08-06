
import json
from pathlib import Path

from tiff.trace_net_engineering_gemma_draft_adapter_v1 import (
    build_engineering_gemma_draft_adapter,
    check_engineering_gemma_draft_adapter_quality,
    _parse_ollama_think,
)


def _write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _draft_packet_payload():
    return {
        "quality_status": "PASS",
        "records": [
            {
                "draft_packet_id": "engineering_draft_packet_0001",
                "question_id": "q1",
                "user_question": "Find part number 120-29073-001 and nearby similar parts.",
                "intent_family": "exact_part_lookup",
                "selected_playbook_id": "part_number_evidence_pack",
                "prompt_contract": {
                    "system_role": "You are an engineering evidence drafting assistant for TRACE-Net.",
                    "non_negotiable_rules": ["Do not invent relationships.", "This is draft-only."],
                    "user_question": "Find part number 120-29073-001 and nearby similar parts.",
                    "selected_playbook": {"selected_playbook_id": "part_number_evidence_pack"},
                    "structured_user_intent": {"seed_entities": ["120-29073-001"]},
                    "draft_instruction_block": {"draft_instructions": ["Start with exact source-backed evidence."]},
                    "source_truth_evidence": [{"route": "table", "excerpt": "120-29073-001 LATERAL STRUCTURE"}],
                    "candidate_evidence": [{"route": "graph", "excerpt": "same assembly neighbor"}],
                    "missing_evidence": [],
                    "forbidden_claims": ["approved replacement"],
                    "answer_format_contract": {"answer_mode": "exact_evidence_first_then_related_context"},
                    "self_rag_summary": {"evidence_strength_score": 90},
                },
                "ready_for_gemma_draft": True,
                "ready_for_final_answer": False,
                "answer_permission": False,
            }
        ],
    }


def test_build_ollama_adapter_payload_defaults_think_false(tmp_path):
    draft = tmp_path / "draft_packet.json"
    _write(draft, _draft_packet_payload())

    payload = build_engineering_gemma_draft_adapter(
        draft_packet_path=draft,
        output_dir=tmp_path / "out",
        provider="ollama",
        base_url="http://127.0.0.1:11434",
        model_id="gemma4:26b",
        api_key="ollama",
        temperature=0,
        max_output_tokens=700,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["adapter_record_count"] == 1
    record = payload["records"][0]
    assert record["model_id"] == "gemma4:26b"
    assert record["ollama_think"] is False
    assert record["request_payload"]["think"] is False
    assert record["request_payload"]["model"] == "gemma4:26b"
    assert record["llm_call_allowed"] is False
    assert Path(record["request_payload_path"]).exists()


def test_build_ollama_adapter_payload_can_enable_think(tmp_path):
    draft = tmp_path / "draft_packet.json"
    _write(draft, _draft_packet_payload())

    payload = build_engineering_gemma_draft_adapter(
        draft_packet_path=draft,
        output_dir=tmp_path / "out",
        provider="ollama",
        model_id="gemma4:26b",
        ollama_think=True,
    )

    record = payload["records"][0]
    assert record["request_payload"]["think"] is True


def test_build_openai_compatible_payload_omits_think(tmp_path):
    draft = tmp_path / "draft_packet.json"
    _write(draft, _draft_packet_payload())

    payload = build_engineering_gemma_draft_adapter(
        draft_packet_path=draft,
        output_dir=tmp_path / "out",
        provider="openai_compatible",
        base_url="http://localhost:8080",
        model_id="trace-net-gemma-draft",
        api_key="blank",
        temperature=0,
        max_output_tokens=500,
    )

    record = payload["records"][0]
    assert record["endpoint"] == "http://localhost:8080/v1/chat/completions"
    assert "think" not in record["request_payload"]


def test_quality_checker_passes_with_think_false_required(tmp_path):
    draft = tmp_path / "draft_packet.json"
    _write(draft, _draft_packet_payload())
    build_engineering_gemma_draft_adapter(draft_packet_path=draft, output_dir=tmp_path / "out")
    report = tmp_path / "out" / "trace_net_engineering_gemma_draft_adapter_v1.json"

    result = check_engineering_gemma_draft_adapter_quality(
        report_path=report,
        require_source_draft_packet_quality_pass=True,
        min_adapter_records=1,
        min_request_payloads_written=1,
        max_request_sent=0,
        max_ready_for_final_answer=0,
        require_ollama_think_false=True,
        require_no_answer_permission=True,
        require_no_llm_calls=True,
        require_no_retrieval_execution=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"


def test_parse_ollama_think_values():
    assert _parse_ollama_think("false") is False
    assert _parse_ollama_think("true") is True
    assert _parse_ollama_think("low") == "low"
