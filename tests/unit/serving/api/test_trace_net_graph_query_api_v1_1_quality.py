import json
from pathlib import Path

from tiff.trace_net_graph_query_api_v1_1 import (
    QualityThresholds,
    build_graph_query_api_v1_1_report,
    check_graph_query_api_v1_1_quality,
)


def helper_payload():
    return {
        "quality_status": "PASS",
        "summary": {"graph_node_count": 10, "graph_edge_count": 20, "source_resolved_result_count": 3},
        "query_records": [
            {"query_type": "part_lookup", "input": {"part_number": "120-46137-001"}, "pages": [{"page_id": "p340", "source_resolved": True}], "can_answer_directly": False, "can_prove_claims": False},
            {"query_type": "page_lookup", "input": {"page_id_or_label": "p003"}, "pages": [{"page_id": "p003", "source_resolved": True}]},
            {"query_type": "ata_browse", "input": {"ata_code": "25-21-00"}, "pages": [{"page_id": "p001", "source_resolved": True}]},
        ],
    }


def enrichment_payload():
    return {
        "quality_status": "PASS",
        "summary": {
            "enriched_query_record_count": 3,
            "enriched_page_record_count": 9,
            "evidence_enriched_page_count": 9,
            "source_resolved_page_count": 9,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "query_records": helper_payload()["query_records"],
        "enriched_page_records": [{"page_id": "p340", "source_resolved": True}],
    }


def write_payload(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_quality_check_passes_existing_report(tmp_path: Path):
    helper = write_payload(tmp_path / "helper.json", helper_payload())
    enrichment = write_payload(tmp_path / "enrichment.json", enrichment_payload())
    report = build_graph_query_api_v1_1_report(
        graph_query_helper_path=helper,
        graph_query_evidence_enrichment_path=enrichment,
        output_dir=tmp_path / "out",
        thresholds=QualityThresholds(require_no_answer_permission=True),
        quality=True,
    )
    checked = check_graph_query_api_v1_1_quality(
        tmp_path / "out" / "trace_net_graph_query_api_v1_1.json",
        thresholds=QualityThresholds(require_no_answer_permission=True),
        write_json_report=True,
    )
    assert report["quality_status"] == "PASS"
    assert checked["quality_status"] == "PASS"


def test_quality_fails_when_enriched_pages_too_low(tmp_path: Path):
    helper = write_payload(tmp_path / "helper.json", helper_payload())
    bad_enrichment = enrichment_payload()
    bad_enrichment["summary"]["evidence_enriched_page_count"] = 0
    enrichment = write_payload(tmp_path / "enrichment.json", bad_enrichment)
    report = build_graph_query_api_v1_1_report(
        graph_query_helper_path=helper,
        graph_query_evidence_enrichment_path=enrichment,
        output_dir=tmp_path / "out",
        thresholds=QualityThresholds(min_evidence_enriched_pages=1),
        quality=True,
    )
    assert report["quality_status"] == "FAIL"
    assert "evidence_enriched_page_count_below_minimum" in report["quality_failures"]


def test_quality_fails_on_answer_permission(tmp_path: Path):
    helper_payload_obj = helper_payload()
    helper_payload_obj["query_records"][0]["can_answer_directly"] = True
    helper = write_payload(tmp_path / "helper.json", helper_payload_obj)
    enrichment = write_payload(tmp_path / "enrichment.json", enrichment_payload())
    report = build_graph_query_api_v1_1_report(
        graph_query_helper_path=helper,
        graph_query_evidence_enrichment_path=enrichment,
        output_dir=tmp_path / "out",
        thresholds=QualityThresholds(require_no_answer_permission=True),
        quality=True,
    )
    assert report["quality_status"] == "FAIL"
    assert any(x.endswith("_must_be_zero") for x in report["quality_failures"])
