import json
from pathlib import Path

from tiff.trace_net_route_dispatch_processor_contract_v1 import build_route_dispatch_processor_contract_report
from tiff.trace_net_route_dispatch_processor_contract_v1_quality import RouteDispatchProcessorContractQualityThresholds


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_processor_contract_builds_allowlists(tmp_path: Path) -> None:
    dispatch = tmp_path / "dispatch.json"
    audit = tmp_path / "audit.json"
    triage = tmp_path / "triage.json"

    _write_json(dispatch, {
        "schema_version": "trace_net_route_dispatch_manifest_v1",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS"},
        "route_dispatch_cards": [
            {
                "page_id": "p1",
                "source_page_id": "metadata_page_000001",
                "page_number": 1,
                "primary_route": "table",
                "primary_dispatch_route": "table",
                "allowed_dispatch_routes": ["table", "image_visual"],
                "table_processing_allowed": True,
                "image_visual_processing_allowed": True,
                "normal_text_processing_allowed": False,
                "blank_candidate_processing_allowed": False,
                "review_processing_required": False,
                "safe_for_routing": True,
                "route_policies": {
                    "table": {"reasons": ["primary_route_table"]},
                    "image_visual": {"reasons": ["secondary_image"]},
                },
            },
            {
                "page_id": "p2",
                "source_page_id": "metadata_page_000002",
                "page_number": 2,
                "primary_route": "blank_candidate",
                "primary_dispatch_route": "blank_candidate",
                "allowed_dispatch_routes": ["blank_candidate", "review"],
                "table_processing_allowed": False,
                "image_visual_processing_allowed": False,
                "normal_text_processing_allowed": False,
                "blank_candidate_processing_allowed": True,
                "review_processing_required": True,
                "safe_for_routing": True,
            },
        ],
    })
    _write_json(audit, {
        "schema_version": "trace_net_route_dispatch_coverage_audit_v1",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS", "route_dispatch_violation_card_count": 0, "route_dispatch_warning_card_count": 2},
    })
    _write_json(triage, {
        "schema_version": "trace_net_route_dispatch_warning_triage_v1",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS", "warning_triage_card_count": 2, "unresolved_violation_triage_count": 0},
    })

    report = build_route_dispatch_processor_contract_report(
        route_dispatch_manifest_path=dispatch,
        route_dispatch_coverage_audit_path=audit,
        route_dispatch_warning_triage_path=triage,
        output_dir=tmp_path / "out",
        thresholds=RouteDispatchProcessorContractQualityThresholds(
            min_processor_contract_cards=2,
            min_source_page_processor_contract_cards=2,
            min_table_processor_pages=1,
            min_image_visual_processor_pages=1,
            require_route_dispatch_manifest_quality_pass=True,
            require_route_dispatch_coverage_audit_quality_pass=True,
            require_route_dispatch_warning_triage_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["processor_contract_card_count"] == 2
    assert report["summary"]["table_processor_allowed_page_count"] == 1
    assert report["summary"]["image_visual_processor_allowed_page_count"] == 1
    assert report["summary"]["blank_candidate_processor_allowed_page_count"] == 1
    assert (tmp_path / "out" / "table_allowed_pages.json").exists()
    assert (tmp_path / "out" / "image_visual_allowed_pages.json").exists()


def test_unsafe_dispatch_blocks_contract_routes(tmp_path: Path) -> None:
    dispatch = tmp_path / "dispatch.json"
    audit = tmp_path / "audit.json"
    triage = tmp_path / "triage.json"

    _write_json(dispatch, {
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS"},
        "route_dispatch_cards": [
            {
                "page_id": "p1",
                "source_page_id": "metadata_page_000001",
                "primary_route": "table",
                "primary_dispatch_route": "table",
                "allowed_dispatch_routes": ["table"],
                "table_processing_allowed": True,
                "safe_for_routing": False,
                "unsafe_dispatch_card": True,
            }
        ],
    })
    _write_json(audit, {"quality_status": "PASS", "summary": {"quality_status": "PASS", "route_dispatch_violation_card_count": 0}})
    _write_json(triage, {"quality_status": "PASS", "summary": {"quality_status": "PASS"}})

    report = build_route_dispatch_processor_contract_report(
        route_dispatch_manifest_path=dispatch,
        route_dispatch_coverage_audit_path=audit,
        route_dispatch_warning_triage_path=triage,
        output_dir=tmp_path / "out",
        thresholds=RouteDispatchProcessorContractQualityThresholds(max_unsafe_contract_cards=1),
    )

    card = report["processor_contract_cards"][0]
    assert card["unsafe_contract_card"] is True
    assert card["processor_allowed_routes"] == []
