import json
from pathlib import Path

from tiff.trace_net_corrective_retrieval_planner_v1 import (
    Thresholds,
    build_corrective_retrieval_plan,
)


def write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_builds_records_from_eval_and_trace_pack(tmp_path):
    page_eval = {
        "quality_status": "PASS",
        "status": "PAGE_RETRIEVAL_LARGE_EVAL_V2_BUILT",
        "summary": {"query_record_count": 2},
        "query_records": [
            {
                "record_id": "qr1",
                "query_id": "q1",
                "page_id": "t_p_1",
                "semantic_retrieval_query": "find page 1",
                "evaluated": True,
                "target_hit_at_k": False,
                "target_rank": None,
                "top_hits": [],
            },
            {
                "record_id": "qr2",
                "query_id": "q2",
                "page_id": "t_p_2",
                "semantic_retrieval_query": "find page 2",
                "evaluated": True,
                "target_hit_at_k": True,
                "target_rank": 9,
                "blank_expected": True,
                "top_hits": [{}] * 9,
            },
        ],
    }
    trace = {
        "quality_status": "PASS",
        "status": "AI_TRACE_PACK_BUILT",
        "trace_pack_records": [
            {
                "trace_pack_id": "tp1",
                "query_id": "part",
                "query": "120-1",
                "trace_status": "TRACE_PACK_REVIEW_RECOMMENDED",
                "needs_review": True,
                "review_reason_codes": ["claim_evidence_review", "page_alignment_review"],
                "page_ids": ["t_p_3"],
            }
        ],
    }
    payload = build_corrective_retrieval_plan(
        output_dir=tmp_path / "out",
        page_retrieval_large_eval_v2=write(tmp_path / "eval.json", page_eval),
        ai_trace_pack=write(tmp_path / "trace.json", trace),
        thresholds=Thresholds(min_correction_records=3, min_review_routed_records=2, require_no_answer_permission=True),
    )
    assert payload["quality_status"] == "PASS"
    records = payload["corrective_retrieval_records"]
    assert len(records) == 3
    assert {r["issue_type"] for r in records} >= {
        "semantic_page_target_miss",
        "target_page_low_rank",
        "trace_pack_review_recommended",
    }
    assert all(not r["can_answer_directly"] for r in records)
    assert all(not r["can_prove_claims"] for r in records)


def test_opensearch_pass_adds_exact_channel_record(tmp_path):
    opensearch = {
        "quality_status": "PASS",
        "status": "LOADER_SMOKE_READY",
        "summary": {"opensearch_document_count": 7027, "query_plan_count": 3},
    }
    payload = build_corrective_retrieval_plan(
        output_dir=tmp_path / "out",
        opensearch_loader_smoke=write(tmp_path / "os.json", opensearch),
        thresholds=Thresholds(min_correction_records=1, require_opensearch_loader_quality_pass=True),
    )
    assert payload["quality_status"] == "PASS"
    record = payload["corrective_retrieval_records"][0]
    assert record["issue_type"] == "exact_search_channel_available"
    assert "use_opensearch_exact_for_identifiers" in record["recommended_actions"]


def test_tiff_review_records_route_to_visual_review(tmp_path):
    audit = {
        "quality_status": "PASS",
        "content_audit_records": [
            {
                "record_id": "r1",
                "page_id": "t_p_7",
                "question": "What is on page 7?",
                "content_audit_status": "REVIEW",
                "vision_evaluated": True,
                "vision_verdict": "REVIEW",
                "heuristic_flags": ["vision_review"],
            }
        ],
    }
    payload = build_corrective_retrieval_plan(
        output_dir=tmp_path / "out",
        page_query_response_tiff_content_audit=write(tmp_path / "audit.json", audit),
        thresholds=Thresholds(min_correction_records=1, min_review_routed_records=1, require_tiff_audit_quality_pass=True),
    )
    assert payload["quality_status"] == "PASS"
    record = payload["corrective_retrieval_records"][0]
    assert record["issue_type"] == "tiff_content_audit_review"
    assert "route_to_tiff_content_review" in record["recommended_actions"]


def test_quality_fails_when_required_quality_is_not_pass(tmp_path):
    page_eval = {"quality_status": "FAIL", "query_records": []}
    payload = build_corrective_retrieval_plan(
        output_dir=tmp_path / "out",
        page_retrieval_large_eval_v2=write(tmp_path / "eval.json", page_eval),
        thresholds=Thresholds(require_page_eval_quality_pass=True),
    )
    assert payload["quality_status"] == "FAIL"
    assert any(c["check_name"] == "page_retrieval_large_eval_v2_quality_pass" and not c["passed"] for c in payload["quality_checks"])
