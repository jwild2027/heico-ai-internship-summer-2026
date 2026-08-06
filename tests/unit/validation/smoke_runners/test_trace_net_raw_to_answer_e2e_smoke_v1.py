import json
from pathlib import Path

from tiff.trace_net_raw_to_answer_e2e_smoke_v1 import (
    build_pipeline_command,
    build_raw_to_answer_e2e_smoke,
    local_retrieve,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def make_artifacts(root: Path) -> None:
    write_json(root / "trace_net_ocr_classifier_pipeline_runner_v1.json", {
        "quality_status": "PASS",
        "summary": {
            "all_stage_quality_pass": True,
            "stage_count": 9,
            "stage_report_count": 9,
            "stage_quality_statuses": {"ocr": "PASS", "retrieval_payload_audit": "PASS"},
        },
    })
    write_json(root / "ocr_route_scan_pack_tesseract_full/trace_net_ocr_route_scan_pack_v1.json", {
        "quality_status": "PASS",
        "records": [
            {"page_id": "p1", "page_number": 1, "ocr_text": "Part number 120-29073-001 appears in this table."},
            {"page_id": "p2", "page_number": 2, "ocr_text": "Plain procedure text."},
        ],
    })
    write_json(root / "retrieval_payload_audit/trace_net_retrieval_payload_audit_v1.json", {
        "quality_status": "PASS",
        "summary": {
            "qdrant_payload_count": 450,
            "opensearch_payload_count": 282,
            "violation_record_count": 0,
            "route_payload_mismatch_count": 0,
        },
        "qdrant_payload_audit_records": [
            {
                "page_id": "p1",
                "page_number": 1,
                "route": "table",
                "source_member": "00000001.tif",
                "raw_tiff_reference": "00000001.tif",
                "source_image_sha256": "abc",
                "storage_decision": "validated_graph_semantic_and_exact_index",
                "payload_id": "p1::qdrant::0001",
                "part_number_count": 1,
                "ocr_char_count": 200,
            }
        ],
        "opensearch_payload_audit_records": [
            {
                "page_id": "p1",
                "page_number": 1,
                "route": "table",
                "source_member": "00000001.tif",
                "raw_tiff_reference": "00000001.tif",
                "source_image_sha256": "abc",
                "storage_decision": "validated_graph_semantic_and_exact_index",
                "payload_id": "p1::opensearch::0001",
                "part_number_count": 1,
                "ocr_char_count": 200,
            }
        ],
    })
    write_json(root / "four_route_storage_gate/trace_net_four_route_storage_gate_v1.json", {
        "quality_status": "PASS",
        "summary": {
            "final_validated_route_counts": {"blank": 14, "plain_text": 163, "table": 320, "image": 12},
            "postgres_graph_record_count": 509,
            "qdrant_embedding_allowed_count": 450,
            "opensearch_index_allowed_count": 282,
        },
    })
    write_json(root / "loader_contract_audit/trace_net_loader_contract_audit_v1.json", {
        "quality_status": "PASS",
        "summary": {
            "postgres_contract_ready_count": 509,
            "qdrant_contract_ready_count": 450,
            "opensearch_contract_ready_count": 282,
            "lineage_ready_count": 509,
            "missing_lineage_count": 0,
        },
    })


def test_build_pipeline_command_uses_existing_runner():
    cmd = build_pipeline_command(
        source_package=Path("metadata.zip"),
        tesseract_cmd=Path("tesseract.exe"),
        output_dir=Path("out"),
    )
    assert "scripts/operations/ocr/run_trace_net_ocr_classifier_pipeline_v1.py" in cmd
    assert "--source-package" in cmd
    assert "--quality" in cmd


def test_local_retrieve_matches_part_number():
    retrieval_payload = {
        "qdrant_payload_audit_records": [
            {"page_id": "p1", "page_number": 1, "route": "table", "source_member": "1.tif", "source_image_sha256": "abc", "part_number_count": 1}
        ],
        "opensearch_payload_audit_records": [],
    }
    ocr_payload = {"records": [{"page_id": "p1", "page_number": 1, "ocr_text": "120-29073-001"}]}
    results = local_retrieve(question="Find 120-29073-001", retrieval_payload=retrieval_payload, ocr_payload=ocr_payload)
    assert results
    assert results[0]["page_id"] == "p1"
    assert results[0]["retrieval_score"] >= 100


def test_build_smoke_from_existing_artifacts(tmp_path):
    make_artifacts(tmp_path)
    payload = build_raw_to_answer_e2e_smoke(
        source_package=Path("metadata.zip"),
        tesseract_cmd=Path("tesseract.exe"),
        output_dir=tmp_path,
        question="Find part number 120-29073-001",
        skip_pipeline=True,
        quality=True,
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["retrieval_evidence_count"] >= 1
    assert payload["summary"]["citation_count"] >= 1
    assert payload["summary"]["postgres_contract_ready_count"] == 509
    assert (tmp_path / "trace_net_raw_to_answer_e2e_smoke_v1_answer.md").exists()


def test_openai_compatible_records_empty_content_reasoning_truncation(monkeypatch):
    from tiff import trace_net_raw_to_answer_e2e_smoke_v1 as smoke

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return json.dumps({
                "model": "gemma4:26b",
                "choices": [{
                    "message": {"content": "", "reasoning": "thinking..."},
                    "finish_reason": "length",
                }],
            }).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(smoke.urlrequest, "urlopen", fake_urlopen)
    result = smoke._call_openai_compatible(
        base_url="http://127.0.0.1:11434/v1",
        model="gemma4:26b",
        api_key="ollama",
        prompt="hello",
        timeout=300,
        max_tokens=2048,
    )

    assert result["ok"] is False
    assert result["llm_finish_reason"] == "length"
    assert result["llm_reasoning_char_count"] > 0
    assert result["llm_fallback_reason"] == "empty_content_reasoning_truncated_increase_llm_max_tokens"
    assert captured["body"]["max_tokens"] == 2048
    assert captured["body"]["stream"] is False


def test_build_smoke_can_require_llm_success(tmp_path, monkeypatch):
    from tiff import trace_net_raw_to_answer_e2e_smoke_v1 as smoke

    make_artifacts(tmp_path)

    def fake_answer(**kwargs):
        return "Gemma answer with citations.", {
            "llm_called": True,
            "llm_status": "PASS",
            "content": "Gemma answer with citations.",
            "llm_model": "gemma4:26b",
            "llm_base_url": "http://127.0.0.1:11434/v1",
            "llm_content_char_count": 27,
            "llm_max_tokens": kwargs.get("llm_max_tokens"),
        }

    monkeypatch.setattr(smoke, "build_answer_draft", fake_answer)
    payload = smoke.build_raw_to_answer_e2e_smoke(
        source_package=Path("metadata.zip"),
        tesseract_cmd=Path("tesseract.exe"),
        output_dir=tmp_path,
        question="Find part number 120-29073-001",
        skip_pipeline=True,
        quality=True,
        llm_mode="ollama_openai",
        llm_max_tokens=2048,
        require_llm_success=True,
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["llm_status"] == "PASS"
    assert payload["summary"]["llm_answer_char_count"] > 0
    assert payload["summary"]["require_llm_success"] is True
