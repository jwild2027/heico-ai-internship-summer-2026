from __future__ import annotations

import json
from pathlib import Path

from tiff import trace_net_ask_hybrid_flag_v1 as mod


def safe_report() -> dict:
    return {
        "schema_version": "trace_net_ask_hybrid_flag_v1",
        "status": "ASK_RAN",
        "quality_status": "PASS",
        "query": "manual revision history",
        "summary": {
            "retrieval_mode": "hybrid-simulate",
            "answer_status": "NOT_COMPOSED_SIMULATION_ONLY",
            "regression_quality_status": "PASS",
            "hybrid_quality_status": "PASS",
            "ranked_group_count": 2,
            "safe_group_count": 2,
            "unsafe_group_count": 0,
            "direct_answer_allowed_group_count": 0,
            "claim_proof_allowed_group_count": 0,
            "source_truth_mutation_allowed_group_count": 0,
            "source_resolution_required_false_count": 0,
            "citation_required_false_count": 0,
            "authority_gate_required_false_count": 0,
            "embedding_dim": 1024,
        },
    }


def test_quality_passes_for_safe_report() -> None:
    result = mod.evaluate_ask_hybrid_flag_quality(safe_report())
    assert result.status == "PASS"
    assert all(check["status"] == "OK" for check in result.checks)


def test_quality_fails_for_direct_answer_permission() -> None:
    report = safe_report()
    report["summary"]["direct_answer_allowed_group_count"] = 1
    result = mod.evaluate_ask_hybrid_flag_quality(report)
    assert result.status == "FAIL"
    assert any(check["name"] == "direct_answer_blocked" and check["status"] == "FAIL" for check in result.checks)


def test_quality_fails_for_wrong_mode() -> None:
    report = safe_report()
    report["summary"]["retrieval_mode"] = "off"
    result = mod.evaluate_ask_hybrid_flag_quality(report)
    assert result.status == "FAIL"


def test_check_quality_writes_json(tmp_path: Path) -> None:
    report_path = tmp_path / "trace_net_ask_hybrid_flag_v1.json"
    report_path.write_text(json.dumps(safe_report()), encoding="utf-8")
    result = mod.check_trace_net_ask_hybrid_flag_quality(report_path=report_path, write_json_report=True)
    assert result["status"] == "PASS"
    assert Path(result["quality_path"]).exists()
