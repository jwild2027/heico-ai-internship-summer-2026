from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_engineering_engram_postgres_feedback_ledger_v1 import (
    build_feedback_ledger_manifest,
    check_feedback_ledger_manifest,
    SCHEMA_SQL,
)


def _write(path: Path, data: dict):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _fixtures(tmp_path: Path):
    answer = {
        "quality_status": "PASS",
        "records": [
            {"question_id": "q12", "question": "interchange?", "grade": "GOOD", "answer_preview": "safe [A1]"},
            {"question_id": "q25", "question": "unknown?", "grade": "PARTIAL", "answer_preview": "not found"},
        ],
    }
    critic = {
        "quality_status": "PASS",
        "critic_records": [
            {"question_id": "q12", "critic_status": "PASS", "findings": ["critic_checks_passed"], "repair_hints": []},
            {"question_id": "q25", "critic_status": "EXPECTED_BOUNDARY", "expected_unknown_boundary_partial": True, "findings": ["expected_unknown_boundary_partial"], "repair_hints": []},
        ],
    }
    crag = {
        "quality_status": "PASS",
        "crag_repair_records": [
            {"question_id": "q12", "crag_status": "NO_REPAIR_NEEDED", "repair_attempted": False},
            {"question_id": "q25", "crag_status": "EXPECTED_BOUNDARY_NO_REPAIR", "repair_attempted": False},
        ],
    }
    return (
        _write(tmp_path / "answer.json", answer),
        _write(tmp_path / "critic.json", critic),
        _write(tmp_path / "crag.json", crag),
    )


def test_schema_has_tables():
    assert "trace_net_engram_feedback_ledger_v1" in SCHEMA_SQL
    assert "trace_net_engram_memory_candidate_v1" in SCHEMA_SQL
    assert "answer_permission BOOLEAN NOT NULL DEFAULT FALSE" in SCHEMA_SQL


def test_build_feedback_ledger_manifest(tmp_path: Path):
    answer, critic, crag = _fixtures(tmp_path)
    result = build_feedback_ledger_manifest(
        answer_smoke=answer,
        critic=critic,
        crag_repair=crag,
        output_dir=tmp_path / "out",
        min_feedback_records=2,
        min_candidate_records=2,
        require_source_quality_pass=True,
        require_critic_quality_pass=True,
        require_crag_quality_pass=True,
        require_no_answer_permission=True,
        max_unsafe=0,
        max_write_attempts=0,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["feedback_record_count"] == 2
    assert result["summary"]["candidate_record_count"] == 2
    assert result["summary"]["write_attempt_count"] == 0
    assert result["summary"]["answer_permission_count"] == 0


def test_check_feedback_ledger_manifest(tmp_path: Path):
    answer, critic, crag = _fixtures(tmp_path)
    result = build_feedback_ledger_manifest(answer, critic, crag, tmp_path / "out", min_feedback_records=2, min_candidate_records=2)
    checked = check_feedback_ledger_manifest(
        tmp_path / "out" / "trace_net_engineering_engram_postgres_feedback_ledger_v1.json",
        min_feedback_records=2,
        min_candidate_records=2,
        require_quality_pass=True,
        require_no_answer_permission=True,
        max_unsafe=0,
        max_write_attempts=0,
    )
    assert checked["quality_status"] == "PASS"


def test_live_postgres_write_is_gated_and_counts_as_write_attempt(tmp_path: Path):
    answer, critic, crag = _fixtures(tmp_path)
    result = build_feedback_ledger_manifest(
        answer,
        critic,
        crag,
        tmp_path / "out",
        enable_live_postgres_write=True,
        min_feedback_records=2,
        min_candidate_records=2,
        max_write_attempts=1,
        max_unsafe=1,
    )
    assert result["summary"]["postgres_write_attempt_count"] == 1
    assert result["summary"]["write_attempt_count"] == 1
    assert result["summary"]["unsafe_finding_count"] == 1
