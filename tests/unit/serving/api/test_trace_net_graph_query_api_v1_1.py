import json
from pathlib import Path

from tiff.trace_net_graph_query_api_v1_1 import (
    QualityThresholds,
    build_graph_query_api_v1_1_report,
    find_part_record,
    parse_include_evidence,
    safe_response_record,
)


def helper_payload():
    return {
        "quality_status": "PASS",
        "status": "GRAPH_QUERY_HELPER_BUILT",
        "summary": {
            "graph_node_count": 10,
            "graph_edge_count": 20,
            "source_resolved_result_count": 3,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "query_records": [
            {
                "query_type": "part_lookup",
                "plan_id": "part_source_check_v1",
                "input": {"part_number": "120-46137-001"},
                "pages": [{"page_id": "p340", "source_resolved": True}],
                "result_count": 1,
                "source_resolved_result_count": 1,
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
            {
                "query_type": "page_lookup",
                "plan_id": "page_source_context_v1",
                "input": {"page_id_or_label": "p003"},
                "pages": [{"page_id": "p003", "source_resolved": True}],
                "result_count": 1,
                "source_resolved_result_count": 1,
            },
            {
                "query_type": "ata_browse",
                "plan_id": "ata_pages_browse_v1",
                "input": {"ata_code": "25-21-00"},
                "pages": [{"page_id": "p001", "source_resolved": True}],
                "result_count": 1,
                "source_resolved_result_count": 1,
            },
        ],
        "page_result_records": [
            {"page_id": "p340", "source_resolved": True},
            {"page_id": "p003", "source_resolved": True},
            {"page_id": "p001", "source_resolved": True},
        ],
    }


def enrichment_payload():
    enriched = helper_payload()
    enriched["schema_version"] = "trace_net_graph_query_evidence_enrichment_v1"
    enriched["quality_status"] = "PASS"
    enriched["status"] = "GRAPH_QUERY_EVIDENCE_ENRICHMENT_BUILT"
    enriched["summary"] = {
        "enriched_query_record_count": 3,
        "enriched_page_record_count": 9,
        "unique_enriched_page_count": 8,
        "evidence_enriched_page_count": 9,
        "source_resolved_page_count": 9,
        "opensearch_exact_channel_count": 4,
        "hybrid_v2_channel_count": 2,
        "leiden_navigation_channel_count": 3,
        "claim_entailment_channel_count": 1,
        "review_record_count": 1,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }
    enriched["query_records"][0]["pages"] = [
        {"page_id": "p340", "source_resolved": True, "channels": ["organization_graph"]},
        {"page_id": "p003", "source_resolved": True, "channels": ["opensearch_exact"]},
        {"page_id": "p339", "source_resolved": True, "channels": ["hybrid_v2_ranked_group"]},
    ]
    enriched["enriched_page_records"] = [
        {"page_id": "p340", "source_resolved": True},
        {"page_id": "p003", "source_resolved": True},
        {"page_id": "p339", "source_resolved": True},
    ]
    enriched["review_records"] = [{"review_type": "claim_evidence_alignment_review"}]
    return enriched


def write_payload(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_find_part_record():
    record = find_part_record(helper_payload(), "120-46137-001")
    assert record is not None
    assert record["result_count"] == 1


def test_parse_include_evidence():
    assert parse_include_evidence({"include_evidence": ["true"]}) is True
    assert parse_include_evidence({"include_evidence": ["0"]}) is False
    assert parse_include_evidence({}, {"include_evidence": True}) is True


def test_safe_response_record_never_grants_answer_permission():
    record = {"pages": [{"page_id": "p1", "can_answer_directly": True}], "can_answer_directly": True}
    safe = safe_response_record(record, view="test")
    assert safe["can_answer_directly"] is False
    assert safe["can_prove_claims"] is False
    assert safe["pages"][0]["can_answer_directly"] is False


def test_build_report_pass(tmp_path: Path):
    helper = write_payload(tmp_path / "helper.json", helper_payload())
    enrichment = write_payload(tmp_path / "enrichment.json", enrichment_payload())
    report = build_graph_query_api_v1_1_report(
        graph_query_helper_path=helper,
        graph_query_evidence_enrichment_path=enrichment,
        output_dir=tmp_path / "out",
        thresholds=QualityThresholds(
            require_helper_quality_pass=True,
            require_enrichment_quality_pass=True,
            require_no_answer_permission=True,
        ),
        quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["include_evidence_enabled_route_count"] == 4
    assert (tmp_path / "out" / "trace_net_graph_query_api_v1_1.json").exists()
