from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_e2e_context_pack_builder_v1 import build_report, evaluate_quality, write_outputs


def _runtime_fixture() -> dict:
    return {
        "quality_status": "PASS",
        "runtime_contract": {"ready_for_context_pack": True},
        "summary": {
            "e2e_hybrid_retrieval_runtime_status": "E2E_HYBRID_RETRIEVAL_RUNTIME_READY_FOR_CONTEXT_PACK",
            "total_retrieval_hit_count": 4,
        },
        "retrieval_groups": [
            {
                "query_id": "q1",
                "query_intent": "covered_part_number",
                "user_query": "Find part number 120-36833-001",
                "retrieval_status": "RETRIEVAL_MATCHED",
                "hits": [
                    {"page_id": "p3", "field_name": "covered_part_number", "normalized_value": "120-36833-001", "retrieval_score": 99, "routing_boost": 1.35},
                    {"page_id": "p3", "field_name": "covered_part_number", "normalized_value": "120-36833-003", "retrieval_score": 50, "routing_boost": 1.35},
                ],
            },
            {
                "query_id": "q2",
                "query_intent": "manual_page_reference",
                "user_query": "Where is manual reference 25-21-00 used?",
                "retrieval_status": "RETRIEVAL_MATCHED",
                "hits": [
                    {"page_id": "p5", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "retrieval_score": 88, "routing_boost": 1.25},
                    {"page_id": "p27", "field_name": "ipl_part_number", "normalized_value": "25-21-00", "retrieval_score": 80, "routing_boost": 1.3},
                ],
            },
        ],
    }


def _args(**kwargs):
    defaults = dict(
        min_source_retrieval_groups=2,
        min_context_packs=2,
        min_context_packs_with_items=2,
        min_total_context_items=4,
        min_pages_with_context_items=2,
        min_citation_ready_items=4,
        min_source_trace_ready_items=4,
        min_field_count=3,
        max_unsafe_records=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_source_runtime_quality_pass=True,
        require_no_answer_permission=True,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_build_report_creates_context_packs(tmp_path: Path):
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text(json.dumps(_runtime_fixture()), encoding="utf-8")
    report = build_report(runtime_path, tmp_path / "out", top_k=2, args=_args())
    assert report["quality_status"] == "PASS"
    assert report["e2e_context_pack_status"] == "E2E_CONTEXT_PACK_READY_FOR_FINAL_GATE"
    assert report["summary"]["context_pack_count"] == 2
    assert report["summary"]["total_context_item_count"] == 4
    assert report["summary"]["citation_ready_context_item_count"] == 4
    assert report["summary"]["source_trace_ready_context_item_count"] == 4
    assert report["summary"]["answer_permission_count"] == 0
    assert report["summary"]["can_answer_directly_count"] == 0
    assert report["summary"]["can_prove_claims_count"] == 0
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0


def test_context_items_are_retrieval_only(tmp_path: Path):
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text(json.dumps(_runtime_fixture()), encoding="utf-8")
    report = build_report(runtime_path, tmp_path / "out", top_k=2, args=_args())
    for item in report["context_items"]:
        assert item["retrieval_only"] is True
        assert item["answer_permission"] is False
        assert item["can_answer_directly"] is False
        assert item["can_prove_claims"] is False
        assert item["source_truth_mutation_allowed"] is False
        assert item["citation_ready"] is True
        assert item["source_trace_ready"] is True
        assert item["schema_complete"] is True


def test_write_outputs(tmp_path: Path):
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text(json.dumps(_runtime_fixture()), encoding="utf-8")
    out = tmp_path / "out"
    report = build_report(runtime_path, out, top_k=2, args=_args())
    write_outputs(report, out)
    assert (out / "trace_net_e2e_context_pack_builder_v1.json").exists()
    assert (out / "trace_net_e2e_context_pack_builder_v1_quality.json").exists()
    assert (out / "trace_net_e2e_context_packs_v1.jsonl").exists()
    assert (out / "trace_net_e2e_context_items_v1.jsonl").exists()
    assert (out / "trace_net_e2e_context_pack_builder_v1_inspect.md").exists()


def test_quality_fails_when_context_items_missing(tmp_path: Path):
    runtime = _runtime_fixture()
    runtime["retrieval_groups"][0]["hits"] = []
    runtime["retrieval_groups"][1]["hits"] = []
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
    report = build_report(runtime_path, tmp_path / "out", top_k=2, args=_args(min_total_context_items=1))
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["context_pack_with_items_count"] == 0


def test_evaluate_quality_is_deterministic(tmp_path: Path):
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text(json.dumps(_runtime_fixture()), encoding="utf-8")
    report = build_report(runtime_path, tmp_path / "out", top_k=2, args=_args())
    status, checks = evaluate_quality(report, _args())
    assert status == "PASS"
    assert all(check["passed"] for check in checks)
