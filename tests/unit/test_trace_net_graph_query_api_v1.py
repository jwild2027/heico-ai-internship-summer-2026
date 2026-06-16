from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_graph_query_api_v1 import (
    GraphQueryService,
    check_graph_query_api_quality,
    make_api_report,
)


def _sample_helper(path: Path, *, quality_status: str = "PASS") -> Path:
    payload = {
        "schema_version": "trace_net_graph_query_helper_v1",
        "status": "GRAPH_QUERY_HELPER_BUILT",
        "quality_status": quality_status,
        "summary": {
            "graph_node_count": 10,
            "graph_edge_count": 20,
            "query_record_count": 3,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "query_records": [
            {
                "plan_id": "part_source_check_v1",
                "query_type": "part_lookup",
                "input": {"part_number": "120-46137-001"},
                "result_count": 1,
                "source_resolved_result_count": 1,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "pages": [
                    {
                        "page_id": "t_p_120_1176_p000340",
                        "ata_codes": ["25-21-00"],
                        "source_links": [{"source_uri": "http://localhost:8080/rescarta/t_p_120_1176/000340"}],
                        "source_resolved": True,
                    }
                ],
            },
            {
                "plan_id": "page_source_context_v1",
                "query_type": "page_lookup",
                "input": {"page_id_or_label": "t_p_120_1176_p000003"},
                "result_count": 1,
                "source_resolved_result_count": 1,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "pages": [{"page_id": "t_p_120_1176_p000003", "source_resolved": True}],
            },
            {
                "plan_id": "ata_pages_browse_v1",
                "query_type": "ata_browse",
                "input": {"ata_code": "25-21-00"},
                "result_count": 2,
                "source_resolved_result_count": 2,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "pages": [
                    {"page_id": "t_p_120_1176_p000001", "source_resolved": True},
                    {"page_id": "t_p_120_1176_p000002", "source_resolved": True},
                ],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_make_api_report_writes_expected_files(tmp_path: Path) -> None:
    helper = _sample_helper(tmp_path / "helper.json")
    out_dir = tmp_path / "api"
    report = make_api_report(helper, out_dir)

    assert report["quality_status"] == "PASS"
    assert report["summary"]["route_record_count"] == 5
    assert report["summary"]["query_record_count"] == 3
    assert (out_dir / "trace_net_graph_query_api_v1.json").exists()
    assert (out_dir / "trace_net_graph_query_api_v1_quality.json").exists()
    assert (out_dir / "trace_net_graph_query_api_v1_routes.jsonl").exists()


def test_service_finds_part_page_and_ata_records(tmp_path: Path) -> None:
    helper = _sample_helper(tmp_path / "helper.json")
    service = GraphQueryService(helper)

    part_status, part_payload = service.query("part_lookup", "120-46137-001")
    assert part_status == 200
    assert part_payload["pages"][0]["page_id"] == "t_p_120_1176_p000340"

    page_status, page_payload = service.query("page_lookup", "t_p_120_1176_p000003")
    assert page_status == 200
    assert page_payload["pages"][0]["page_id"] == "t_p_120_1176_p000003"

    ata_status, ata_payload = service.query("ata_browse", "25-21-00")
    assert ata_status == 200
    assert ata_payload["result_count"] == 2


def test_not_found_result_is_safe(tmp_path: Path) -> None:
    helper = _sample_helper(tmp_path / "helper.json")
    service = GraphQueryService(helper)

    status, payload = service.query("part_lookup", "DOES-NOT-EXIST")
    assert status == 404
    assert payload["status"] == "GRAPH_QUERY_RESULT_NOT_FOUND"
    assert payload["can_answer_directly"] is False
    assert payload["can_prove_claims"] is False


def test_quality_fails_when_source_query_grants_answer_permission(tmp_path: Path) -> None:
    helper = _sample_helper(tmp_path / "helper.json")
    payload = json.loads(helper.read_text(encoding="utf-8"))
    payload["query_records"][0]["can_answer_directly"] = True
    helper.write_text(json.dumps(payload), encoding="utf-8")

    report = make_api_report(helper)
    quality = check_graph_query_api_quality(
        report,
        thresholds=__import__("tiff.trace_net_graph_query_api_v1", fromlist=["ApiQualityThresholds"]).ApiQualityThresholds(
            require_no_answer_permission=True
        ),
    )
    assert quality["quality_status"] == "FAIL"
    assert quality["failures"]
