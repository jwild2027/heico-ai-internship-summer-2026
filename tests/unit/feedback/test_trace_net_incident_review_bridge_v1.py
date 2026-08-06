from pathlib import Path
import json

from tiff.trace_net_incident_review_bridge_v1 import (
    build_incident_review_bridge,
    make_review_task,
    normalize_incident,
)


def test_normalize_incident_defaults_and_safety() -> None:
    incident = normalize_incident({
        "origin_category": "visual_diagram",
        "severity": "review",
        "message": "Callout needs verification.",
        "page_ids": ["p1"],
    })
    assert incident["incident_id"].startswith("inc__")
    assert incident["origin_category"] == "visual_diagram"
    assert incident["page_ids"] == ["p1"]
    assert incident["can_answer_directly"] is False
    assert incident["can_prove_claims"] is False


def test_make_review_task_from_visual_incident() -> None:
    incident = normalize_incident({
        "incident_id": "inc1",
        "origin_category": "visual_diagram",
        "severity": "review",
        "message": "Verify diagram callouts.",
        "target_type": "page",
        "target_id": "t_p_120_1176_p000003",
        "page_ids": ["t_p_120_1176_p000003"],
    })
    task = make_review_task(incident)
    assert task["task_type"] == "verify_visual_callouts"
    assert task["priority"] == "high"
    assert task["page_id"] == "t_p_120_1176_p000003"
    assert task["can_answer_directly"] is False
    assert task["can_prove_claims"] is False
    assert task["can_mutate_source_truth"] is False


def test_security_incident_escalates_critical() -> None:
    incident = normalize_incident({
        "incident_id": "inc2",
        "origin_category": "security_leakage",
        "severity": "critical",
        "message": "Path leak detected.",
    })
    task = make_review_task(incident)
    assert task["priority"] == "critical"
    assert task["task_type"] == "review_security_leakage_incident"


def test_build_from_jsonl(tmp_path: Path) -> None:
    incident_path = tmp_path / "incidents.jsonl"
    incident_path.write_text(
        json.dumps({
            "incident_id": "inc1",
            "origin_category": "feedback_memory",
            "severity": "critical",
            "message": "Suspicious feedback detected.",
            "target_type": "feedback_memory",
            "target_id": "fb1",
        }) + "\n" +
        json.dumps({
            "incident_id": "inc2",
            "origin_category": "table_extraction",
            "severity": "warning",
            "message": "Table repair should be reviewed.",
            "page_ids": ["p2"],
        }) + "\n",
        encoding="utf-8",
    )
    report = build_incident_review_bridge(
        incidents_jsonl=incident_path,
        output_dir=tmp_path / "out",
        min_incidents=2,
        min_review_tasks=2,
        min_high_priority_tasks=1,
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["incident_count"] == 2
    assert report["summary"]["review_task_count"] == 2
    assert (tmp_path / "out" / "trace_net_incident_review_bridge_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_incident_review_bridge_v1_tasks.jsonl").exists()
