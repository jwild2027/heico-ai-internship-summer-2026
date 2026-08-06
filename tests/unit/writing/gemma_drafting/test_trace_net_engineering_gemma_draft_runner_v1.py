
import json
from pathlib import Path

from tiff.trace_net_engineering_gemma_draft_runner_v1 import (
    build_engineering_gemma_draft_runner,
    check_engineering_gemma_draft_runner_quality,
)


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _adapter_payload(tmp_path):
    request_path = tmp_path / "request_payloads" / "request.json"
    _write(request_path, {
        "model": "gemma3:27b",
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 10},
    })
    return {
        "quality_status": "PASS",
        "records": [
            {
                "adapter_record_id": "adapter_1",
                "source_draft_packet_id": "draft_1",
                "question_id": "q1",
                "user_question": "Find part number 120-29073-001",
                "intent_family": "exact_part_lookup",
                "selected_playbook_id": "part_number_evidence_pack",
                "provider": "ollama",
                "endpoint": "http://127.0.0.1:11434/api/chat",
                "model_id": "gemma3:27b",
                "request_payload_path": str(request_path),
                "answer_permission": False,
            }
        ],
    }


def test_dry_run_runner_does_not_send(tmp_path):
    adapter = tmp_path / "adapter.json"
    _write(adapter, _adapter_payload(tmp_path))

    payload = build_engineering_gemma_draft_runner(
        adapter_report_path=adapter,
        output_dir=tmp_path / "out",
        execute=False,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["runner_record_count"] == 1
    assert payload["summary"]["request_sent_count"] == 0
    assert payload["summary"]["response_received_count"] == 0
    assert payload["summary"]["ready_for_final_answer_count"] == 0
    record = payload["records"][0]
    assert record["draft_response_status"] == "dry_run_not_sent"
    assert record["llm_call_allowed"] is False
    assert Path(record["draft_response_path"]).exists()


def test_quality_checker_passes_for_dry_run(tmp_path):
    adapter = tmp_path / "adapter.json"
    _write(adapter, _adapter_payload(tmp_path))
    build_engineering_gemma_draft_runner(
        adapter_report_path=adapter,
        output_dir=tmp_path / "out",
        execute=False,
    )
    report = tmp_path / "out" / "trace_net_engineering_gemma_draft_runner_v1.json"

    result = check_engineering_gemma_draft_runner_quality(
        report_path=report,
        require_source_adapter_quality_pass=True,
        min_runner_records=1,
        max_ready_for_final_answer=0,
        require_no_answer_permission=True,
        require_no_retrieval_execution=True,
        require_no_source_truth_mutation=True,
        require_dry_run_no_llm_calls=True,
    )
    assert result["quality_status"] == "PASS"
