from pathlib import Path
import json

from tiff.trace_net_incident_review_bridge_v1 import build_incident_review_bridge, quality_report


def write_incidents(path: Path) -> None:
    path.write_text(
        json.dumps({
            "incident_id": "inc1",
            "origin_category": "trust_authority",
            "severity": "critical",
            "message": "Authority issue.",
        }) + "\n",
        encoding="utf-8",
    )


def test_quality_report_passes(tmp_path: Path) -> None:
    incident_path = tmp_path / "incidents.jsonl"
    write_incidents(incident_path)
    report = build_incident_review_bridge(
        incidents_jsonl=incident_path,
        output_dir=tmp_path / "out",
        min_incidents=1,
        min_review_tasks=1,
        min_high_priority_tasks=1,
        write_quality=True,
    )
    quality = quality_report(Path(report["report_path"]), min_incidents=1, min_review_tasks=1, min_high_priority_tasks=1)
    assert quality["status"] == "PASS"
    assert quality["review_task_count"] == 1
    assert quality["critical_priority_review_task_count"] == 1


def test_quality_report_fails_when_no_tasks(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "summary": {
            "incident_count": 0,
            "review_task_count": 0,
            "unsafe_review_task_count": 0,
            "review_task_can_answer_directly_count": 0,
            "review_task_can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
            "missing_target_count": 0,
        }
    }), encoding="utf-8")
    quality = quality_report(report_path, min_incidents=1, min_review_tasks=1)
    assert quality["status"] == "FAIL"


def test_quality_report_fails_for_unsafe_task(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "summary": {
            "incident_count": 1,
            "review_task_count": 1,
            "unsafe_review_task_count": 1,
            "review_task_can_answer_directly_count": 1,
            "review_task_can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
            "missing_target_count": 0,
        }
    }), encoding="utf-8")
    quality = quality_report(report_path, min_incidents=1, min_review_tasks=1)
    assert quality["status"] == "FAIL"
