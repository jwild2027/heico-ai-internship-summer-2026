import json
from pathlib import Path

from tiff.trace_net_e2e_tool_usage_audit_v1 import STATUS_USED, check_audit_quality


def _write_report(path: Path, *, used_tool_count=3, trace=True):
    payload = {
        "quality_status": "PASS",
        "summary": {
            "used_tool_count": used_tool_count,
            "trace_net_present": trace,
            "trace_llm_called": True,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "tool_checklist": [
            {"tool": "webui_endpoint", "status": STATUS_USED},
            {"tool": "gemma_llm", "status": STATUS_USED},
            {"tool": "ocr_fishnet", "status": STATUS_USED},
            {"tool": "page_context_v2", "status": "available_not_used"},
            {"tool": "route_dispatch", "status": "available_not_used"},
            {"tool": "table_route", "status": "available_not_used"},
            {"tool": "embedding_vector", "status": "available_not_used"},
            {"tool": "graph_leiden", "status": "available_not_used"},
            {"tool": "visual_image_route", "status": "available_not_used"},
            {"tool": "self_rag", "status": "available_not_used"},
            {"tool": "crag_retry", "status": "available_not_used"},
            {"tool": "final_gate", "status": "available_not_used"},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_quality_passes_with_required_llm_and_safety(tmp_path):
    path = tmp_path / "report.json"
    _write_report(path)
    result = check_audit_quality(
        report_path=path,
        min_checklist_count=10,
        min_used_tool_count=3,
        require_trace_net=True,
        require_llm_called=True,
        require_tool_statuses={"ocr_fishnet": STATUS_USED},
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert result["quality_status"] == "PASS"
    assert result["failures"] == []


def test_quality_fails_when_required_tool_status_missing(tmp_path):
    path = tmp_path / "report.json"
    _write_report(path)
    result = check_audit_quality(report_path=path, require_tool_statuses={"graph_leiden": STATUS_USED})
    assert result["quality_status"] == "FAIL"
    assert any("graph_leiden" in f for f in result["failures"])


def test_quality_fails_on_answer_permission(tmp_path):
    path = tmp_path / "report.json"
    _write_report(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["summary"]["answer_permission_count"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = check_audit_quality(report_path=path, require_no_answer_permission=True)
    assert result["quality_status"] == "FAIL"
    assert any("answer_permission" in f for f in result["failures"])
