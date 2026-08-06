from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_api_wrapper_smoke_v1 import (
    QualityThresholds,
    build_api_wrapper_smoke,
    build_and_write,
    evaluate_quality,
)


def _demo_record(i: int):
    return {
        "query_id": f"e2e_query_v1_000{i}",
        "query_intent": "covered_part_number" if i % 2 else "manual_page_reference",
        "demo_flow_status": "E2E_DEMO_FLOW_COMPLETE",
        "user_query": f"Find thing {i}",
        "retrieval_hit_count": 10,
        "citation_count": 3,
        "final_gate_decision": "FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT",
        "page_ids": [f"t_p_120_1176_p00000{i}", f"t_p_120_1176_p00010{i}"],
        "response_draft": f"Final-gate smoke draft {i}",
        "citations": [
            {
                "citation_id": f"c{i}_{j}",
                "page_id": f"t_p_120_1176_p00000{i}",
                "field_name": ["covered_part_number", "manual_page_reference", "ipl_text"][j % 3],
                "normalized_value": f"120-36{i}{j}",
                "source_trace_ready": True,
                "citation_ready": True,
            }
            for j in range(3)
        ],
    }


def _source_report():
    return {
        "quality_status": "PASS",
        "summary": {
            "e2e_demo_record_count": 5,
            "complete_demo_flow_count": 5,
            "api_wrapper_next_step": True,
        },
        "demo_contract": {
            "safe_responses_are_drafts_until_api_finalization": True,
            "answer_authority": "blocked_in_artifact_smoke",
        },
        "demo_records": [_demo_record(i) for i in range(1, 6)],
    }


def test_build_api_wrapper_smoke_counts():
    report = build_api_wrapper_smoke(_source_report(), top_k_citations=3)
    s = report["summary"]
    assert report["e2e_api_wrapper_smoke_status"] == "E2E_API_WRAPPER_SMOKE_READY_FOR_LOCAL_ENDPOINT"
    assert s["api_wrapper_request_count"] == 5
    assert s["api_wrapper_response_count"] == 5
    assert s["citation_backed_api_response_count"] == 5
    assert s["total_api_citation_count"] == 15
    assert s["answer_permission_count"] == 0
    assert s["can_answer_directly_count"] == 0
    assert s["can_prove_claims_count"] == 0


def test_api_request_shape_is_openai_compatible():
    report = build_api_wrapper_smoke(_source_report(), top_k_citations=2)
    request = report["api_requests"][0]
    assert request["endpoint"] == "/api/trace-net/ask"
    assert request["openai_compatible_endpoint"] == "/v1/chat/completions"
    assert request["body"]["messages"][0]["role"] == "user"
    assert request["answer_permission"] is False


def test_api_response_citations_are_limited():
    report = build_api_wrapper_smoke(_source_report(), top_k_citations=2)
    response = report["api_responses"][0]
    assert response["api_response_status"] == "citation_backed_response_draft"
    assert response["citation_count"] == 2
    assert response["citations"][0]["citation_ready"] is True
    assert response["can_prove_claims"] is False


def test_quality_passes_with_default_thresholds():
    report = build_api_wrapper_smoke(_source_report(), top_k_citations=3)
    quality = evaluate_quality(
        report,
        QualityThresholds(require_source_demo_quality_pass=True, require_no_answer_permission=True),
    )
    assert quality["quality_status"] == "PASS"


def test_quality_fails_when_not_enough_citations():
    report = build_api_wrapper_smoke(_source_report(), top_k_citations=1)
    quality = evaluate_quality(report, QualityThresholds(min_total_api_citations=20))
    assert quality["quality_status"] == "FAIL"


def test_build_and_write_outputs(tmp_path: Path):
    source_path = tmp_path / "source.json"
    import json

    source_path.write_text(json.dumps(_source_report()), encoding="utf-8")
    report = build_and_write(
        e2e_rag_demo_report_path=source_path,
        output_dir=tmp_path / "out",
        top_k_citations=3,
        thresholds=QualityThresholds(require_source_demo_quality_pass=True, require_no_answer_permission=True),
    )
    assert report["quality_status"] == "PASS"
    assert (tmp_path / "out" / "trace_net_e2e_api_wrapper_smoke_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_e2e_api_wrapper_smoke_responses_v1.jsonl").exists()
    assert (tmp_path / "out" / "trace_net_e2e_api_wrapper_smoke_v1_inspect.md").exists()
