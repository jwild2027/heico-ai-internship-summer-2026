from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_dublin_core_source_package_extension_v1 import check_quality


def test_quality_report_passes_for_clean_report(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    payload = {
        "quality_status": "PASS",
        "summary": {
            "status": "PASS",
            "page_record_count": 2,
            "document_record_count": 1,
            "metadata_xml_present": True,
            "pages_with_source_package_entry_count": 2,
            "missing_source_package_entry_count": 0,
            "checksum_mismatch_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "quality_checks": {
                "page_count_matches_required": True,
                "min_page_records_met": True,
                "min_pages_with_source_package_entry_met": True,
                "metadata_xml_present": True,
                "checksum_mismatch_count_zero": True,
                "source_truth_mutation_allowed_count_zero": True,
                "direct_answer_allowed_count_zero": True,
                "claim_proof_allowed_count_zero": True,
            },
        },
        "quality_path": str(tmp_path / "quality.json"),
    }
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    quality = check_quality(
        report_path=report_path,
        require_page_count=2,
        min_page_records=2,
        min_pages_with_source_package_entry=2,
        require_metadata_xml=True,
        write_json_report=True,
    )
    assert quality["status"] == "PASS"
    assert (tmp_path / "quality.json").exists()


def test_quality_report_fails_on_checksum_mismatch(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    payload = {
        "quality_status": "FAIL",
        "summary": {
            "status": "FAIL",
            "page_record_count": 1,
            "document_record_count": 1,
            "metadata_xml_present": True,
            "pages_with_source_package_entry_count": 1,
            "checksum_mismatch_count": 1,
            "source_truth_mutation_allowed_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "quality_checks": {"checksum_mismatch_count_zero": False},
        },
    }
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    quality = check_quality(report_path=report_path, min_pages_with_source_package_entry=1)
    assert quality["status"] == "FAIL"
