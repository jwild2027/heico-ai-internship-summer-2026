from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_e2e_evidence_sufficiency_gate_v1 import (
    AUDIT_ONLY_STATUS,
    QUALITY_PASS,
    SUFFICIENT_STATUS,
    build_gate_record,
    build_report,
    evaluate_quality,
    write_outputs,
)


def _item(page: str = "p1", field: str = "covered_part_number", value: str = "120-36833-001") -> dict:
    return {
        "page_id": page,
        "field_name": field,
        "normalized_value": value,
        "citation_ready": True,
        "source_trace_ready": True,
        "schema_complete": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "unsafe": False,
    }


def _context_pack(query_id: str = "q1", items: int = 5) -> dict:
    fields = ["covered_part_number", "manual_page_reference", "ipl_part_number", "ipl_text", "ipl_figure_item_or_quantity"]
    return {
        "context_pack_id": f"pack_{query_id}",
        "query_id": query_id,
        "query_intent": "covered_part_number",
        "user_query": f"Find thing {query_id}",
        "top_context_items": [_item(f"p{i % 3 + 1}", fields[i % len(fields)], f"value-{query_id}-{i}") for i in range(items)],
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "unsafe": False,
    }


def _source_report(pack_count: int = 5) -> dict:
    packs = [_context_pack(f"q{i}", 5) for i in range(pack_count)]
    return {
        "quality_status": "PASS",
        "e2e_context_pack_status": "E2E_CONTEXT_PACK_READY_FOR_FINAL_GATE",
        "context_pack_contract": {"ready_for_final_gate": True},
        "summary": {
            "context_pack_count": pack_count,
            "context_pack_with_items_count": pack_count,
            "total_context_item_count": pack_count * 5,
            "all_context_retrieval_only": True,
        },
        "context_packs": packs,
    }


def _args(**overrides):
    defaults = dict(
        min_items_per_pack=3,
        min_citation_ready_items_per_pack=3,
        min_source_trace_ready_items_per_pack=3,
        min_source_context_packs=5,
        min_context_packs_with_items=5,
        min_evidence_gate_records=5,
        min_sufficient_context_packs=4,
        min_final_gate_ready_packs=4,
        min_total_evidence_items=20,
        min_citation_ready_evidence_items=20,
        min_source_trace_ready_evidence_items=20,
        min_pages_with_evidence_items=2,
        min_field_count=3,
        max_unsafe_records=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_source_context_pack_quality_pass=True,
        require_no_answer_permission=True,
        quality=True,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_build_gate_record_marks_sufficient_pack_ready_for_final_gate_review():
    rec = build_gate_record(
        _context_pack("q1", 5),
        min_items_per_pack=3,
        min_citation_ready_items_per_pack=3,
        min_source_trace_ready_items_per_pack=3,
    )
    assert rec["evidence_sufficiency_status"] == SUFFICIENT_STATUS
    assert rec["sufficient_for_final_gate_review"] is True
    assert rec["answer_permission"] is False
    assert rec["can_answer_directly"] is False
    assert rec["can_prove_claims"] is False


def test_build_gate_record_marks_weak_pack_audit_only():
    rec = build_gate_record(
        _context_pack("q1", 1),
        min_items_per_pack=3,
        min_citation_ready_items_per_pack=3,
        min_source_trace_ready_items_per_pack=3,
    )
    assert rec["evidence_sufficiency_status"] == AUDIT_ONLY_STATUS
    assert rec["audit_only"] is True
    assert rec["audit_reasons"]


def test_build_report_passes_for_sample_context_packs(tmp_path: Path):
    source_path = tmp_path / "context.json"
    source_path.write_text(json.dumps(_source_report(5)), encoding="utf-8")
    report = build_report(source_path, tmp_path / "out", _args())
    assert report["quality_status"] == QUALITY_PASS
    summary = report["summary"]
    assert summary["evidence_sufficiency_gate_record_count"] == 5
    assert summary["sufficient_context_pack_count"] == 5
    assert summary["final_gate_review_ready_pack_count"] == 5
    assert summary["answer_permission_count"] == 0
    assert summary["can_answer_directly_count"] == 0


def test_quality_fails_when_answer_permission_leaks(tmp_path: Path):
    source = _source_report(5)
    source["context_packs"][0]["top_context_items"][0]["answer_permission"] = True
    source_path = tmp_path / "context.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    report = build_report(source_path, tmp_path / "out", _args())
    assert report["quality_status"] != QUALITY_PASS
    names = {c["name"]: c for c in report["quality_checks"]}
    assert names["answer_permission_count"]["passed"] is False


def test_write_outputs_creates_expected_files(tmp_path: Path):
    source_path = tmp_path / "context.json"
    source_path.write_text(json.dumps(_source_report(5)), encoding="utf-8")
    out = tmp_path / "out"
    report = build_report(source_path, out, _args())
    write_outputs(report, out)
    assert (out / "trace_net_e2e_evidence_sufficiency_gate_v1.json").exists()
    assert (out / "trace_net_e2e_evidence_sufficiency_gate_records_v1.jsonl").exists()
    assert (out / "trace_net_e2e_evidence_sufficiency_gate_v1_inspect.md").exists()


def test_evaluate_quality_reads_summary_thresholds(tmp_path: Path):
    source_path = tmp_path / "context.json"
    source_path.write_text(json.dumps(_source_report(5)), encoding="utf-8")
    report = build_report(source_path, tmp_path / "out", _args())
    status, checks = evaluate_quality(report, _args())
    assert status == QUALITY_PASS
    assert all(c["passed"] for c in checks)
