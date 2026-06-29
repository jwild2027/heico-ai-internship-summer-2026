import json
from pathlib import Path

from tiff import trace_net_raw_to_answer_e2e_smoke_native_v1 as mod


def test_build_retrieval_evidence_exact_part_match():
    contract = {
        "records": [
            {
                "page_id": "p1",
                "page_number": 10,
                "route": "table",
                "qdrant_contract_ready": True,
                "opensearch_contract_ready": True,
                "contract_ready_targets": ["qdrant", "opensearch"],
                "source_member": "00000010.tif",
                "source_image_sha256": "abc",
            }
        ]
    }
    scan = {"records": [{"page_id": "p1", "ocr_text": "Part 120-29073-001 is listed near 120-29073-002."}]}
    records = mod.build_retrieval_evidence(question="Find 120-29073-001", contract_payload=contract, scan_payload=scan)
    assert len(records) == 1
    assert records[0]["page_id"] == "p1"
    assert records[0]["retrieval_score"] >= 1000
    assert "120-29073-001" in records[0]["part_numbers"]


def test_call_ollama_native_success(monkeypatch):
    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps({"message": {"content": "Hello final."}, "done_reason": "stop"}).encode()

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda req, timeout: FakeResponse())
    result = mod.call_ollama_native(
        base_url="http://127.0.0.1:11434",
        model="gemma4:26b",
        prompt="hello",
        request_timeout=1,
        think=False,
        num_predict=32,
        temperature=0,
    )
    assert result["llm_status"] == "PASS"
    assert result["answer_text"] == "Hello final."
    assert result["llm_think"] is False


def test_call_ollama_native_empty_content_fallback(monkeypatch):
    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps({"message": {"content": "", "thinking": "hidden"}, "done_reason": "length"}).encode()

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda req, timeout: FakeResponse())
    result = mod.call_ollama_native(
        base_url="http://127.0.0.1:11434",
        model="gemma4:26b",
        prompt="hello",
        request_timeout=1,
        think=False,
        num_predict=32,
        temperature=0,
    )
    assert result["llm_status"] == "FALLBACK"
    assert result["llm_fallback_reason"] == "empty_native_content"
    assert result["llm_reasoning_char_count"] > 0


def test_check_quality_requires_llm_success(tmp_path):
    report = tmp_path / mod.REPORT_NAME
    payload = {
        "quality_status": "PASS",
        "summary": {
            "stage_report_count": 9,
            "postgres_contract_ready_count": 509,
            "qdrant_contract_ready_count": 450,
            "opensearch_contract_ready_count": 282,
            "qdrant_payload_count": 450,
            "opensearch_payload_count": 282,
            "retrieval_evidence_count": 8,
            "citation_count": 8,
            "violation_record_count": 0,
            "all_stage_quality_pass": True,
            "dry_run_only": True,
            "human_review_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
            "llm_status": "FALLBACK",
            "llm_answer_char_count": 0,
        },
    }
    report.write_text(json.dumps(payload), encoding="utf-8")
    result = mod.check_quality(report_path=report, require_llm_success=True)
    assert result["quality_status"] == "FAIL"
