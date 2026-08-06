from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_route_contract_integration_audit_v1 import (
    AuditThresholds,
    build_route_contract_integration_audit_report,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_route_contract_integration_audit_passes_for_allowed_outputs(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    write_json(contract, {
        "quality_status": "PASS",
        "table_allowed_pages": ["p1"],
        "image_visual_allowed_pages": ["p2"],
        "normal_text_allowed_pages": ["p3"],
    })

    table = tmp_path / "table.json"
    visual = tmp_path / "visual.json"
    callout = tmp_path / "callout.json"
    page_context = tmp_path / "page_context.jsonl"
    helpers = tmp_path / "helpers.json"
    pack = tmp_path / "pack.json"

    write_json(table, {"quality_status": "PASS", "table_geometry_cards": [{"page_id": "p1", "can_answer_directly": False}]})
    write_json(visual, {"quality_status": "PASS", "records": [{"page_id": "p2"}]})
    write_json(callout, {"quality_status": "PASS", "records": [{"page_id": "p2"}]})
    page_context.write_text(json.dumps({"page_id": "p3"}) + "\n", encoding="utf-8")
    write_json(helpers, {"quality_status": "PASS", "records": [{"page_id": "p3"}]})
    write_json(pack, {"quality_status": "PASS", "records": [{"page_id": "p3", "answer_composition_allowed": False}]})

    report = build_route_contract_integration_audit_report(
        route_dispatch_processor_contract=contract,
        output_dir=tmp_path / "out",
        table_line_geometry=table,
        visual_ink_layout_calibrator=visual,
        callout_visual_part_verifier=callout,
        page_context_v2_records=page_context,
        context_retrieval_helpers=helpers,
        answer_context_pack=pack,
        thresholds=AuditThresholds(min_audited_processors=6, min_audited_records=6),
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["route_contract_violation_card_count"] == 0
    assert report["summary"]["unsafe_audit_card_count"] == 0


def test_route_contract_integration_audit_fails_for_wrong_route_output(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    write_json(contract, {
        "quality_status": "PASS",
        "table_allowed_pages": ["p1"],
        "image_visual_allowed_pages": [],
        "normal_text_allowed_pages": [],
    })

    table = tmp_path / "table.json"
    empty_json = tmp_path / "empty.json"
    empty_jsonl = tmp_path / "empty.jsonl"

    write_json(table, {"table_geometry_cards": [{"page_id": "not_allowed"}]})
    write_json(empty_json, {"records": []})
    empty_jsonl.write_text("", encoding="utf-8")

    report = build_route_contract_integration_audit_report(
        route_dispatch_processor_contract=contract,
        output_dir=tmp_path / "out",
        table_line_geometry=table,
        visual_ink_layout_calibrator=empty_json,
        callout_visual_part_verifier=empty_json,
        page_context_v2_records=empty_jsonl,
        context_retrieval_helpers=empty_json,
        answer_context_pack=empty_json,
        thresholds=AuditThresholds(min_audited_processors=1, min_audited_records=1),
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["route_contract_violation_card_count"] == 1
