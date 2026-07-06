import json
from pathlib import Path

from tiff.trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1 import (
    build_overlay_integration_gate,
    check_overlay_integration_gate,
)


def _write(path: Path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _fixtures(tmp_path: Path):
    qids = ["q12", "q16", "q18", "q25", "q29"]
    overlay_records = []
    h25_records = []
    source_records = []
    for qid in qids:
        overlay_records.append({
            "question_id": qid,
            "source_question": f"Question {qid}",
            "source_grade": "GOOD" if qid != "q25" else "PARTIAL",
            "matched_bridge_query_ids": ["h19_q"],
            "matched_bridge_task_types": ["summary_limit"],
            "selected_layers": ["working_memory"],
            "selected_proof_roles": ["guidance_only"],
            "overlay_text": "Use this overlay as behavior guidance only. It is not proof. Manual/source claims still require current proof_context citations.",
            "unsafe": False,
            "answer_permission": False,
        })
        h25_records.append({
            "question_id": qid,
            "grade": "GOOD",
            "answer_permission": False,
            "unsafe": False,
        })
        source_records.append({
            "question_id": qid,
            "question": f"Question {qid}",
            "grade": "GOOD" if qid != "q25" else "PARTIAL",
        })
    overlay = {
        "quality_status": "PASS",
        "summary": {"unsafe_finding_count": 0, "answer_permission_count": 0, "write_attempt_count": 0},
        "overlay_records": overlay_records,
    }
    h25 = {
        "quality_status": "PASS",
        "summary": {"good_answer_count": 5, "bad_answer_count": 0, "unsupported_claim_count": 0, "answer_permission_count": 0, "write_attempt_count": 0},
        "smoke_records": h25_records,
    }
    source = {
        "quality_status": "PASS",
        "summary": {"good_answer_count": 28, "partial_answer_count": 2},
        "records": source_records,
    }
    return (
        _write(tmp_path / "overlay.json", overlay),
        _write(tmp_path / "h25.json", h25),
        _write(tmp_path / "source.json", source),
    )


def test_build_gate_passes(tmp_path):
    overlay, h25, source = _fixtures(tmp_path)
    result = build_overlay_integration_gate(
        overlay_smoke=overlay,
        overlay_llm_smoke=h25,
        source_answer_smoke=source,
        output_dir=tmp_path / "out",
        require_h24_quality_pass=True,
        require_h25_quality_pass=True,
        require_source_answer_smoke_quality_pass=True,
        require_no_answer_permission=True,
        max_unsafe=0,
        max_write_attempts=0,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["gate_record_count"] == 5
    assert result["summary"]["overlay_map_record_count"] == 5
    assert result["summary"]["unsafe_finding_count"] == 0
    assert Path(result["paths"]["overlay_map"]).exists()


def test_check_gate_passes(tmp_path):
    overlay, h25, source = _fixtures(tmp_path)
    result = build_overlay_integration_gate(
        overlay_smoke=overlay,
        overlay_llm_smoke=h25,
        source_answer_smoke=source,
        output_dir=tmp_path / "out",
        require_h24_quality_pass=True,
        require_h25_quality_pass=True,
        require_source_answer_smoke_quality_pass=True,
        require_no_answer_permission=True,
    )
    checked = check_overlay_integration_gate(
        integration_gate=tmp_path / "out" / "trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1.json",
        min_gate_records=5,
        min_overlay_map_records=5,
        require_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert checked["quality_status"] == "PASS"
    assert checked["status"].endswith("CHECKED")


def test_missing_boundary_fails(tmp_path):
    overlay, h25, source = _fixtures(tmp_path)
    data = json.loads(overlay.read_text(encoding="utf-8"))
    data["overlay_records"][0]["overlay_text"] = "guidance"
    overlay.write_text(json.dumps(data), encoding="utf-8")
    result = build_overlay_integration_gate(
        overlay_smoke=overlay,
        overlay_llm_smoke=h25,
        source_answer_smoke=source,
        output_dir=tmp_path / "out",
        max_unsafe=0,
    )
    assert result["quality_status"] == "FAIL"
    assert result["summary"]["unsafe_finding_count"] == 1


def test_overlay_map_requires_explicit_flag(tmp_path):
    overlay, h25, source = _fixtures(tmp_path)
    result = build_overlay_integration_gate(
        overlay_smoke=overlay,
        overlay_llm_smoke=h25,
        source_answer_smoke=source,
        output_dir=tmp_path / "out",
    )
    for rec in result["gate_records"]:
        assert rec["requires_explicit_cli_flag"] is True
        assert rec["real_answer_smoke_overlay_enabled"] is False
