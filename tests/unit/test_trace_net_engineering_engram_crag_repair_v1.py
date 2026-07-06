import json
from pathlib import Path

from tiff.trace_net_engineering_engram_crag_repair_v1 import (
    build_artifact_repair_answer,
    build_crag_repair_manifest,
    check_crag_repair_manifest,
    critic_recommends_repair,
)


def _write(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _answer_smoke(tmp_path: Path):
    return _write(tmp_path / "answer.json", {
        "quality_status": "PASS",
        "records": [
            {"question_id": "q12", "question": "interchange?", "grade": "GOOD", "answer_text": "Answer [A1]"},
            {"question_id": "q25", "question": "unknown", "grade": "PARTIAL", "answer_text": "Not source-trace-ready."},
        ],
    })


def _critic(tmp_path: Path, repair=False):
    return _write(tmp_path / "critic.json", {
        "quality_status": "PASS",
        "critic_records": [
            {"question_id": "q12", "source_grade": "GOOD", "critic_status": "PASS", "repair_recommended": False, "repair_hints": []},
            {"question_id": "q25", "source_grade": "PARTIAL", "critic_status": "EXPECTED_BOUNDARY", "expected_unknown_boundary_partial": True, "repair_recommended": False, "repair_hints": []},
            *([{"question_id": "q99", "source_grade": "PARTIAL", "critic_status": "REPAIR_RECOMMENDED", "repair_recommended": True, "repair_hints": ["Add citations."]}] if repair else []),
        ],
    })


def test_critic_recommends_repair():
    assert critic_recommends_repair({"critic_status": "REPAIR_RECOMMENDED"})
    assert critic_recommends_repair({"repair_recommended": True})
    assert not critic_recommends_repair({"critic_status": "PASS"})


def test_build_crag_no_repairs_passes(tmp_path):
    result = build_crag_repair_manifest(
        critic_path=_critic(tmp_path),
        answer_smoke_path=_answer_smoke(tmp_path),
        output_dir=tmp_path / "out",
        min_records=2,
        min_crag_pass_or_no_repair=2,
        max_repair_attempts=0,
        require_source_quality_pass=True,
        require_critic_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["repair_recommended_count"] == 0
    assert result["summary"]["expected_boundary_preserved_count"] == 1


def test_repair_candidate_fails_when_attempts_not_allowed(tmp_path):
    result = build_crag_repair_manifest(
        critic_path=_critic(tmp_path, repair=True),
        answer_smoke_path=_answer_smoke(tmp_path),
        output_dir=tmp_path / "out",
        min_records=3,
        min_crag_pass_or_no_repair=3,
        max_repair_attempts=0,
        require_critic_quality_pass=True,
    )
    assert result["quality_status"] == "FAIL"
    assert result["summary"]["repair_recommended_count"] == 1


def test_artifact_repair_allowed(tmp_path):
    result = build_crag_repair_manifest(
        critic_path=_critic(tmp_path, repair=True),
        answer_smoke_path=_answer_smoke(tmp_path),
        output_dir=tmp_path / "out",
        min_records=3,
        min_crag_pass_or_no_repair=3,
        max_repair_attempts=1,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["repair_attempt_count"] == 1
    repaired = [r for r in result["crag_repair_records"] if r["repair_attempted"]][0]
    assert "cannot prove" in repaired["repaired_answer_preview"] or "cannot create proof" in result["crag_policy"]["proof_boundary"]


def test_check_crag(tmp_path):
    result = build_crag_repair_manifest(
        critic_path=_critic(tmp_path),
        answer_smoke_path=_answer_smoke(tmp_path),
        output_dir=tmp_path / "out",
        min_records=2,
        min_crag_pass_or_no_repair=2,
    )
    checked = check_crag_repair_manifest(
        crag_repair=Path(result["outputs"]["manifest"]),
        min_records=2,
        min_crag_pass_or_no_repair=2,
        require_quality_pass=True,
        require_no_answer_permission=True,
        max_repair_attempts=0,
    )
    assert checked["quality_status"] == "PASS"
