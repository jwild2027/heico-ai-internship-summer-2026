from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_relationship_final_gate_hardener_v30 import (
    build_report,
    detect_relationship_gate_issues,
)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_detects_graph_as_proof_violation():
    rec = {
        "user_query": "Explain how part A relates to manual B",
        "response_mode": "relationship_synthesis",
        "relationship_query": True,
        "final_answer": "The Leiden community proves this relationship.",
    }
    issues = detect_relationship_gate_issues(rec)
    assert issues["graph_as_proof_violation"] is True
    assert issues["unsupported_relationship_claim"] is True


def test_safe_guidance_answer_does_not_trigger_violation():
    rec = {
        "user_query": "What pages are related to part number 120-36833-503?",
        "response_mode": "relationship_navigation",
        "relationship_query": True,
        "final_answer": "Candidate pages are guidance only, not proof. Confirm candidate pages with source-truth evidence.",
    }
    issues = detect_relationship_gate_issues(rec)
    assert issues["relationship_gate_issue_count"] == 0


def test_detects_v2_and_nomenclature_proof_violations():
    v2 = {
        "user_query": "Does the v2 summary prove this?",
        "response_mode": "relationship_synthesis",
        "relationship_query": True,
        "final_answer": "The V2 summary confirms the relationship.",
    }
    nom = {
        "user_query": "What does the nomenclature mean?",
        "response_mode": "relationship_synthesis",
        "relationship_query": True,
        "final_answer": "The nomenclature means this part is connected to the manual.",
    }
    assert detect_relationship_gate_issues(v2)["v2_summary_as_proof_violation"] is True
    assert detect_relationship_gate_issues(nom)["nomenclature_as_proof_violation"] is True


def test_build_report_repairs_synthetic_violations(tmp_path: Path):
    source = tmp_path / "source.json"
    _write_json(
        source,
        {
            "module": "fake_v29_2",
            "quality_status": "PASS",
            "sample_records": [
                {
                    "user_query": "What pages are related to part number 120-36833-503?",
                    "response_mode": "relationship_navigation",
                    "relationship_query": True,
                    "final_answer": "Graph/Leiden output is guidance only, not proof. Confirm candidate pages with source-truth evidence.",
                }
            ],
        },
    )
    report = build_report(
        relationship_router_hardening=source,
        output_dir=tmp_path / "out",
        include_synthetic_violations=True,
        min_relationship_final_gates=4,
        min_passed_relationship_final_gates=4,
        min_relationship_records=4,
        min_repaired_relationship_answers=3,
        max_post_gate_issue_count=0,
        require_no_answer_permission=True,
        quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["relationship_final_gate_count"] == 4
    assert report["repaired_relationship_answer_count"] >= 3
    assert report["post_gate_issue_count"] == 0
    assert Path(report["report_path"]).exists()
    assert Path(report["records_jsonl_path"]).exists()
    assert Path(report["inspect_md_path"]).exists()


def test_non_relationship_metadata_records_pass_without_repair(tmp_path: Path):
    source = tmp_path / "source.json"
    _write_json(
        source,
        {
            "module": "fake_v29_2",
            "quality_status": "PASS",
            "sample_records": [
                {
                    "user_query": "how many pages have a v2 summary",
                    "response_mode": "artifact_metadata_count",
                    "relationship_query": False,
                    "final_answer": "TRACE-Net found v2 summary guidance for 509 pages. V2 summaries are guidance metadata only, not source-truth proof.",
                }
            ],
        },
    )
    report = build_report(
        relationship_router_hardening=source,
        output_dir=tmp_path / "out",
        include_synthetic_violations=False,
        min_relationship_final_gates=1,
        min_passed_relationship_final_gates=1,
        min_relationship_records=0,
        min_repaired_relationship_answers=0,
        max_post_gate_issue_count=0,
        require_no_answer_permission=True,
        quality=True,
    )
    rec = report["relationship_final_gate_records"][0]
    assert rec["repaired_from_draft"] is False
    assert rec["final_gate_status"] == "RELATIONSHIP_FINAL_GATE_PASS"


def test_report_fails_when_post_gate_issues_remain(tmp_path: Path):
    # The normal repair path should make this pass. This regression guard ensures the quality gate is active.
    source = tmp_path / "source.json"
    _write_json(source, {"sample_records": []})
    report = build_report(
        relationship_router_hardening=source,
        output_dir=tmp_path / "out",
        include_synthetic_violations=True,
        min_relationship_final_gates=99,
        quality=True,
    )
    assert report["quality_status"] == "FAIL"
