from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_fishnet_router_hardening_policy_v1 import check_policy_quality


def _report(path: Path, *, policy_count: int = 2, route_auth: int = 0) -> Path:
    payload = {
        "quality_status": "PASS",
        "summary": {
            "source_review_packet_quality_status": "PASS",
            "policy_record_count": policy_count,
            "normal_text_review_promotion_count": policy_count,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "route_change_authorized_count": route_auth,
            "route_manifest_write_allowed_count": 0,
        },
        "records": [],
    }
    p = path / "report.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_quality_passes_for_safe_policy(tmp_path: Path) -> None:
    report = _report(tmp_path)
    result = check_policy_quality(
        report_path=report,
        min_policy_records=2,
        min_normal_text_review_promotions=2,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_route_manifest_write=True,
        require_source_review_packet_quality_pass=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_fails_for_too_few_records(tmp_path: Path) -> None:
    report = _report(tmp_path, policy_count=1)
    result = check_policy_quality(report_path=report, min_policy_records=2)
    assert result["quality_status"] == "FAIL"
    assert "policy_record_count_below_min" in result["failures"]


def test_quality_fails_for_route_authorization(tmp_path: Path) -> None:
    report = _report(tmp_path, policy_count=2, route_auth=1)
    result = check_policy_quality(report_path=report, max_route_change_authorized=0)
    assert result["quality_status"] == "FAIL"
    assert "route_change_authorized_count_above_max" in result["failures"]
