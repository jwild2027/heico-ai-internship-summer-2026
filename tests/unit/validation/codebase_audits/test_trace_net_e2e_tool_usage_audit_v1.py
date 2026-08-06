import json
from pathlib import Path

from tiff.trace_net_e2e_tool_usage_audit_v1 import (
    STATUS_AVAILABLE_NOT_USED,
    STATUS_NOT_AVAILABLE_NOT_USED,
    STATUS_USED,
    build_audit_report,
    build_tool_usage_checklist,
    checklist_text,
)


def _statuses(checklist):
    return {row["tool"]: row["status"] for row in checklist}


def test_checklist_marks_visible_webui_llm_ocr_page_context_and_route_used(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("local_data/organization/trace_net/fishnet_ocr_grid").mkdir(parents=True)
    Path("local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json").write_text("{}", encoding="utf-8")
    response = {
        "choices": [{"message": {"content": "TRACE-Net found page source_p000471."}}],
        "trace_net": {
            "intent": "fallback_search",
            "response_kind": "gemma4_composed_artifact_search",
            "llm_called": True,
            "llm_model": "gemma4:26b",
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "citations": [
                {
                    "page_id": "source_p000471",
                    "page_number": 471,
                    "route": "normal_text",
                    "source": "page_context_v2_or_fishnet",
                }
            ],
        },
    }
    checklist = build_tool_usage_checklist(question="what is page 471", response=response)
    statuses = _statuses(checklist)
    assert statuses["webui_endpoint"] == STATUS_USED
    assert statuses["gemma_llm"] == STATUS_USED
    assert statuses["ocr_fishnet"] == STATUS_USED
    assert statuses["page_context_v2"] == STATUS_USED
    assert statuses["route_dispatch"] == STATUS_USED
    assert statuses["graph_leiden"] in {STATUS_AVAILABLE_NOT_USED, STATUS_NOT_AVAILABLE_NOT_USED}
    text = checklist_text(checklist)
    assert "ocr/fishnet: used" in text
    assert "graph/leiden" in text


def test_checklist_marks_graph_and_embedding_used_when_trace_exposes_sources():
    response = {
        "choices": [{"message": {"content": "Leiden graph and vector similarity found candidates."}}],
        "trace_net": {
            "llm_called": True,
            "llm_model": "gemma4:26b",
            "citations": [
                {"source": "leiden_communities", "route": "normal_text"},
                {"source": "hybrid_vector_embedding", "route": "normal_text"},
            ],
        },
    }
    statuses = _statuses(build_tool_usage_checklist(question="find similar parts", response=response))
    assert statuses["graph_leiden"] == STATUS_USED
    assert statuses["embedding_vector"] == STATUS_USED


def test_build_audit_report_from_saved_response_writes_report(tmp_path):
    response_path = tmp_path / "response.json"
    response_path.write_text(
        json.dumps(
            {
                "choices": [{"message": {"content": "Answer from page source_p000001."}}],
                "trace_net": {
                    "llm_called": False,
                    "answer_permission": False,
                    "source_truth_mutation_allowed": False,
                    "citations": [{"page_id": "source_p000001", "route": "table", "source": "table_exact_search_adapter"}],
                },
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "audit"
    payload = build_audit_report(question="find part", output_dir=out_dir, response_json_path=response_path)
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["tool_checklist_count"] >= 10
    assert "table_route" in payload["summary"]["used_tools"]
    assert (out_dir / "trace_net_e2e_tool_usage_audit_v1.json").exists()
    assert (out_dir / "trace_net_e2e_tool_usage_audit_v1_checklist.txt").exists()


def test_endpoint_call_failure_writes_fail_report(tmp_path):
    payload = build_audit_report(
        question="test",
        output_dir=tmp_path / "audit",
        endpoint_url="http://127.0.0.1:1/v1/chat/completions",
        request_timeout=1,
    )
    assert payload["quality_status"] == "FAIL"
    assert payload["summary"]["call_status"] == "endpoint_call_failed"
