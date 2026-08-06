import json
from pathlib import Path

from tiff.trace_net_dublin_core_crosswalk_v1 import quality_report


def test_quality_report_passes_clean_summary(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"summary": {
        "page_dc_record_count": 509,
        "document_dc_record_count": 1,
        "page_records_with_element_counts": 509,
        "missing_dc_identifier_count": 0,
        "missing_dc_source_count": 0,
        "missing_dc_format_count": 0,
        "missing_trace_net_element_count": 0,
        "missing_trace_net_element_type_count": 0,
        "direct_answer_allowed_count": 0,
        "claim_proof_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }}), encoding="utf-8")
    q = quality_report(report_path=path, quality_config={"require_page_count": 509, "min_pages_with_element_counts": 509}, write_json_report=True)
    assert q["status"] == "PASS"
    assert Path(q["quality_path"]).exists()


def test_quality_report_requires_page_count(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"summary": {
        "page_dc_record_count": 508,
        "document_dc_record_count": 1,
        "page_records_with_element_counts": 508,
        "missing_dc_identifier_count": 0,
        "missing_dc_source_count": 0,
        "missing_dc_format_count": 0,
        "missing_trace_net_element_count": 0,
        "missing_trace_net_element_type_count": 0,
        "direct_answer_allowed_count": 0,
        "claim_proof_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }}), encoding="utf-8")
    q = quality_report(report_path=path, quality_config={"require_page_count": 509})
    assert q["status"] == "FAIL"
