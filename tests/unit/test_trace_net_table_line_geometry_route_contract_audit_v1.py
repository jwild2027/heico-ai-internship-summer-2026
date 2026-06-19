import json
from pathlib import Path

from tiff.trace_net_table_line_geometry_route_contract_audit_v1 import build_table_line_geometry_route_contract_audit_report
from tiff.trace_net_table_line_geometry_route_contract_audit_v1_quality import TableLineGeometryRouteContractAuditQualityThresholds


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _contract_payload():
    return {
        "schema_version": "trace_net_route_dispatch_processor_contract_v1",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS"},
        "processor_contract_cards": [
            {"page_id": "p1", "source_page_id": "metadata_page_000001", "page_number": 1, "table_processing_allowed": True, "review_processing_required": False, "safe_for_routing": True},
            {"page_id": "p2", "source_page_id": "metadata_page_000002", "page_number": 2, "table_processing_allowed": False, "review_processing_required": True, "safe_for_routing": True},
        ],
    }


def test_table_geometry_audit_passes_when_all_cards_allowed(tmp_path: Path):
    table_path = tmp_path / "table_line_geometry.json"
    contract_path = tmp_path / "contract.json"
    _write_json(table_path, {"schema_version": "trace_net_table_line_geometry_v1", "quality_status": "PASS", "table_geometry_cards": [{"page_id": "p1", "table_id": "t1"}]})
    _write_json(contract_path, _contract_payload())

    report = build_table_line_geometry_route_contract_audit_report(
        table_line_geometry_path=table_path,
        route_dispatch_processor_contract_path=contract_path,
        output_dir=tmp_path / "out",
        thresholds=TableLineGeometryRouteContractAuditQualityThresholds(
            min_table_geometry_cards=1,
            min_route_contract_audit_cards=1,
            max_table_route_blocked_geometry_cards=0,
            require_table_line_geometry_quality_pass=True,
            require_route_dispatch_processor_contract_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["table_route_allowed_geometry_card_count"] == 1
    assert report["summary"]["table_route_blocked_geometry_card_count"] == 0


def test_table_geometry_audit_fails_when_card_blocked(tmp_path: Path):
    table_path = tmp_path / "table_line_geometry.json"
    contract_path = tmp_path / "contract.json"
    _write_json(table_path, {"schema_version": "trace_net_table_line_geometry_v1", "quality_status": "PASS", "table_geometry_cards": [{"page_id": "p2", "table_id": "t2"}]})
    _write_json(contract_path, _contract_payload())

    report = build_table_line_geometry_route_contract_audit_report(
        table_line_geometry_path=table_path,
        route_dispatch_processor_contract_path=contract_path,
        output_dir=tmp_path / "out",
        thresholds=TableLineGeometryRouteContractAuditQualityThresholds(max_table_route_blocked_geometry_cards=0),
    )
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["table_route_blocked_geometry_card_count"] == 1
