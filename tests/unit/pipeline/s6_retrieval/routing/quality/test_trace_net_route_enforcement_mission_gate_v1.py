from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_route_enforcement_mission_gate_v1 import (
    MissionGateThresholds,
    build_route_enforcement_mission_gate_report,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_route_enforcement_mission_gate_passes_all_required_artifacts(tmp_path: Path) -> None:
    paths = {}
    for name in [
        "artifact_detector",
        "page_ink",
        "page_route",
        "dispatch",
        "contract",
        "coverage",
    ]:
        path = tmp_path / f"{name}.json"
        write_json(path, {"quality_status": "PASS", "summary": {"quality_status": "PASS"}})
        paths[name] = path

    integration = tmp_path / "integration.json"
    write_json(integration, {
        "quality_status": "PASS",
        "summary": {
            "quality_status": "PASS",
            "route_contract_violation_card_count": 0,
            "blocked_dispatch_leak_count": 0,
            "direct_answer_leak_count": 0,
            "source_truth_mutation_leak_count": 0,
            "unsafe_audit_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    })

    report = build_route_enforcement_mission_gate_report(
        output_dir=tmp_path / "out",
        artifact_detector=paths["artifact_detector"],
        page_ink_route_evidence=paths["page_ink"],
        page_route_manifest=paths["page_route"],
        route_dispatch_manifest=paths["dispatch"],
        route_dispatch_processor_contract=paths["contract"],
        route_dispatch_coverage_audit=paths["coverage"],
        route_contract_integration_audit=integration,
        thresholds=MissionGateThresholds(),
    )

    assert report["quality_status"] == "PASS"
    assert report["status"] == "TRACE_NET_ROUTE_ENFORCEMENT_READY"


def test_route_enforcement_mission_gate_fails_missing_artifact(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    write_json(good, {"quality_status": "PASS", "summary": {"quality_status": "PASS"}})

    report = build_route_enforcement_mission_gate_report(
        output_dir=tmp_path / "out",
        artifact_detector=good,
        page_ink_route_evidence=tmp_path / "missing.json",
        page_route_manifest=good,
        route_dispatch_manifest=good,
        route_dispatch_processor_contract=good,
        route_dispatch_coverage_audit=good,
        route_contract_integration_audit=good,
        thresholds=MissionGateThresholds(),
    )

    assert report["quality_status"] == "FAIL"
    assert "page_ink_route_evidence" in report["summary"]["failed_required_artifacts"]
