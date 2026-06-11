from __future__ import annotations

from pathlib import Path

import pytest

from tiff import trace_net_synthetic_incident_postgres_smoke_v1 as mod


def test_quality_report_passes_for_safe_postgres_summary() -> None:
    report = {
        "status": "POSTGRES_SMOKE_RAN",
        "summary": {
            "storage_mode": "postgres",
            "postgres_table": "trace_net_synthetic_incident_events",
            "inserted_incident_count": 1,
            "created_incident_found_count": 1,
            "unsafe_incident_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
            "affects_real_pipeline_count": 0,
        },
    }
    quality = mod.quality_report(report, min_inserted_incidents=1)
    assert quality["status"] == "PASS"


def test_quality_report_fails_if_not_inserted() -> None:
    report = {
        "status": "POSTGRES_SMOKE_RAN",
        "summary": {
            "storage_mode": "postgres",
            "postgres_table": "trace_net_synthetic_incident_events",
            "inserted_incident_count": 0,
            "created_incident_found_count": 0,
            "unsafe_incident_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
            "affects_real_pipeline_count": 0,
        },
    }
    quality = mod.quality_report(report, min_inserted_incidents=1)
    assert quality["status"] == "FAIL"
    assert quality["checks"]["inserted_incident_count_min"] is False


def test_summarize_created_incidents_counts_unsafe_flags() -> None:
    safe = {
        "incident_id": "a",
        "randomly_generated": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "raw_feedback_direct_to_llm": False,
        "affects_real_pipeline": False,
    }
    unsafe = dict(safe, incident_id="b", raw_feedback_direct_to_llm=True)
    summary = mod.summarize_created_incidents([safe, unsafe])
    assert summary["created_incident_count"] == 2
    assert summary["randomly_generated_incident_count"] == 2
    assert summary["unsafe_incident_count"] == 1
    assert summary["raw_feedback_direct_to_llm_count"] == 1


def test_run_postgres_smoke_with_monkeypatched_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    counts = {"value": 10}
    saved_ids: list[str] = []

    def fake_init(database_url: str, *, table_name: str) -> None:
        assert database_url
        assert table_name

    def fake_count(database_url: str, table_name: str) -> int:
        return counts["value"]

    def fake_save(output_dir: Path, incident: dict, *, storage_mode: str, database_url: str, table_name: str) -> dict:
        saved_ids.append(incident["incident_id"])
        counts["value"] += 1
        return incident

    def fake_fetch(database_url: str, table_name: str, incident_ids: list[str]) -> list[dict]:
        return [{"incident_id": incident_id, "synthetic_only": True, "payload": {}} for incident_id in incident_ids]

    def fake_report(output_dir: Path, *, storage_mode: str, database_url: str, table_name: str) -> dict:
        return {"summary": {"incident_count": counts["value"]}}

    monkeypatch.setattr(mod, "init_postgres_storage", fake_init)
    monkeypatch.setattr(mod, "postgres_count", fake_count)
    monkeypatch.setattr(mod, "save_incident_for_storage", fake_save)
    monkeypatch.setattr(mod, "postgres_fetch_incidents", fake_fetch)
    monkeypatch.setattr(mod, "build_console_report", fake_report)

    report = mod.run_postgres_smoke(
        database_url="postgresql://example",
        output_dir=tmp_path,
        postgres_table="trace_net_synthetic_incident_events",
        random_incident_count=2,
        min_inserted_incidents=2,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["before_count"] == 10
    assert report["summary"]["after_count"] == 12
    assert report["summary"]["inserted_incident_count"] == 2
    assert report["summary"]["created_incident_found_count"] == 2
    assert len(saved_ids) == 2
    assert (tmp_path / "trace_net_synthetic_incident_postgres_smoke_v1.json").exists()
