import json
from pathlib import Path

import pytest

from tiff.trace_net_table_route_evidence_packager_v1 import (
    EvidencePackagingError,
    EvidencePackagerThresholds,
    build_report,
    extract_field_name,
    package_evidence_records,
    render_inspect_markdown,
    write_packager_outputs,
)


def sample_audit_report():
    records = []
    for idx in range(120):
        records.append(
            {
                "search_ready": True,
                "page_id": f"t_p_120_1176_p{idx % 3 + 1:06d}",
                "table_id": f"table_{idx % 5:04d}",
                "field_name": "covered_part_number" if idx < 40 else "ipl_part_number",
                "normalized_value": f"PN-{idx:04d}",
                "raw_value": f"PN {idx:04d}",
                "row_index": idx,
                "column_index": 2,
                "confidence": 0.9,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            }
        )
    records.extend(
        [
            {
                "promotion_status": "search_ready",
                "page_id": "t_p_120_1176_p000004",
                "table_id": "lep_0001",
                "normalized_field": "manual_page_reference",
                "normalized_value": f"32-10-{idx:02d}",
            }
            for idx in range(40)
        ]
    )
    records.extend(
        [
            {
                "promoted_as_evidence": True,
                "page_id": "t_p_120_1176_p000005",
                "table_id": "ipl_0001",
                "role": "ipl_text",
                "text": f"Nomenclature {idx}",
            }
            for idx in range(10)
        ]
    )
    return {
        "quality_status": "PASS",
        "summary": {
            "table_route_value_audit_record_count": 20,
            "search_ready_evidence_record_count": 170,
            "promoted_table_value_evidence_record_count": 170,
            "unsafe_table_route_value_audit_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "records": records,
    }


def relaxed_thresholds():
    return EvidencePackagerThresholds(
        min_source_search_ready_records=100,
        min_evidence_documents=100,
        min_pages_with_evidence=1,
        min_field_count=4,
        min_covered_part_number_documents=40,
        min_manual_page_reference_documents=40,
        min_ipl_part_number_documents=80,
        require_source_audit_quality_pass=True,
        require_no_answer_permission=True,
    )


def test_extract_field_name_normalizes_aliases():
    assert extract_field_name({"role": "part_number"}) == "ipl_part_number"
    assert extract_field_name({"normalized_field": "Manual Page Reference"}) == "manual_page_reference"


def test_package_evidence_records_preserves_safe_contract():
    records = package_evidence_records(sample_audit_report())
    assert len(records) == 170
    assert records[0]["evidence_id"].startswith("table_value_evidence_")
    assert records[0]["retrieval_only"] is True
    assert records[0]["can_answer_directly"] is False
    assert records[0]["can_prove_claims"] is False
    assert records[0]["answer_permission"] is False
    assert records[0]["source_truth_mutation_allowed"] is False
    assert "search_text" in records[0]


def test_package_rejects_answer_authority_leak():
    report = {
        "quality_status": "PASS",
        "records": [
            {
                "search_ready": True,
                "field_name": "ipl_part_number",
                "normalized_value": "123",
                "can_answer_directly": True,
            }
        ],
    }
    with pytest.raises(EvidencePackagingError):
        package_evidence_records(report)


def test_build_report_quality_passes_with_relaxed_thresholds():
    report = build_report(sample_audit_report(), relaxed_thresholds())
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["table_route_evidence_document_count"] == 170
    assert summary["field_counts"]["covered_part_number"] == 40
    assert summary["field_counts"]["manual_page_reference"] == 40
    assert summary["field_counts"]["ipl_part_number"] == 80
    assert summary["field_counts"]["ipl_text"] == 10
    assert summary["answer_permission_count"] == 0
    assert summary["opensearch_write_attempt_count"] == 0


def test_render_inspect_markdown_contains_core_sections():
    report = build_report(sample_audit_report(), relaxed_thresholds())
    text = render_inspect_markdown(report)
    assert "Package counters" in text
    assert "Field counts" in text
    assert "Safety/write counters" in text
    assert "covered_part_number" in text


def test_write_packager_outputs_writes_json_jsonl_and_markdown(tmp_path: Path):
    audit_path = tmp_path / "audit.json"
    out_dir = tmp_path / "out"
    audit_path.write_text(json.dumps(sample_audit_report()), encoding="utf-8")
    report = write_packager_outputs(audit_path, out_dir, relaxed_thresholds())
    assert report["quality_status"] == "PASS"
    assert (out_dir / "trace_net_table_route_evidence_packager_v1.json").exists()
    assert (out_dir / "trace_net_table_route_evidence_documents_v1.jsonl").exists()
    assert (out_dir / "trace_net_table_route_evidence_packager_v1_quality.json").exists()
    assert (out_dir / "trace_net_table_route_evidence_packager_v1_inspect.md").exists()
    assert len((out_dir / "trace_net_table_route_evidence_documents_v1.jsonl").read_text().splitlines()) == 170


def test_packages_nested_search_ready_records_by_parent_path():
    report = {
        "quality_status": "PASS",
        "summary": {
            "table_route_value_audit_record_count": 20,
            "search_ready_evidence_record_count": 4,
            "promoted_table_value_evidence_record_count": 4,
            "unsafe_table_route_value_audit_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "audit_records": [
            {
                "page_id": "t_p_120_1176_p000101",
                "table_id": "table_101",
                "promoted_table_value_evidence_records": [
                    {"field_role": "covered_part_number", "evidence_value": "A123", "row_number": 1},
                    {"field_role": "manual_page_reference", "display_value": "25-21-00", "row_number": 1},
                    {"field_role": "part_number", "text_value": "PN-001", "row_number": 2},
                    {"field_role": "ipl_text", "normalized_text": "BRACKET", "row_number": 2},
                ],
                "context_only_records": [
                    {"field_role": "lep_context", "evidence_value": "noise"},
                ],
            }
        ],
    }
    records = package_evidence_records(report)
    assert len(records) == 4
    assert {r["field_name"] for r in records} == {
        "covered_part_number",
        "manual_page_reference",
        "ipl_part_number",
        "ipl_text",
    }
    assert all(r["retrieval_only"] for r in records)
    assert all(r["answer_permission"] is False for r in records)


def test_nested_negative_parent_path_is_not_packaged():
    report = {
        "quality_status": "PASS",
        "search_ready_evidence_records": [
            {"field_name": "ipl_part_number", "normalized_value": "PN-OK"},
        ],
        "review_required_records": [
            {"field_name": "ipl_part_number", "normalized_value": "PN-NOT-READY"},
        ],
        "context_only_records": [
            {"field_name": "ipl_text", "normalized_value": "noise"},
        ],
    }
    records = package_evidence_records(report)
    assert [r["normalized_value"] for r in records] == ["PN-OK"]
