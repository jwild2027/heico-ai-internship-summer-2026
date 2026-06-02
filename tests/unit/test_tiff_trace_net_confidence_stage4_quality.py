from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_confidence_stage4_quality import Stage4QualityOptions, build_stage4_quality, write_stage4_quality


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_stage4_quality_accepts_safe_simulation(tmp_path: Path) -> None:
    eval_path = tmp_path / "stage4.json"
    _write_json(
        eval_path,
        {
            "status": "OK",
            "version": "trace_lc_stage4_policy_simulation_v1",
            "records": 3,
            "pages": 2,
            "policy_present": True,
            "policy_version": "trace_lc_confidence_policy_v1",
            "policy_layers": 6,
            "policy_rag_include_records": 2,
            "trust_changed_records": 1,
            "rag_action_changed_records": 1,
            "repair_action_changed_records": 1,
            "unsafe_policy_rag_include_records": 0,
            "source_trace_policy_A_records": 2,
            "table_candidate_direct_rag_records": 0,
            "visual_text_above_B_records": 0,
            "policy_trust_tier_counts": {"A": 2, "B": 1},
            "policy_rag_action_counts": {"include_as_source_evidence": 2, "exclude_until_table_tiles_exist": 1},
        },
    )

    report = build_stage4_quality(
        eval_path,
        Stage4QualityOptions(min_records=3, min_pages=2, min_layers=6, min_source_trace_policy_A_records=2),
    )

    assert report.status == "OK"
    assert all(check.ok for check in report.checks)


def test_stage4_quality_fails_unsafe_policy_include(tmp_path: Path) -> None:
    eval_path = tmp_path / "stage4.json"
    _write_json(
        eval_path,
        {
            "status": "OK",
            "version": "trace_lc_stage4_policy_simulation_v1",
            "records": 1,
            "pages": 1,
            "policy_present": True,
            "policy_layers": 6,
            "unsafe_policy_rag_include_records": 1,
            "source_trace_policy_A_records": 0,
            "table_candidate_direct_rag_records": 0,
            "visual_text_above_B_records": 0,
        },
    )

    report = write_stage4_quality(tmp_path / "quality.json", eval_path, Stage4QualityOptions(max_unsafe_policy_rag_include_records=0))

    assert report.status == "FAIL"
    assert (tmp_path / "quality.json").exists()
    assert any(check.name == "stage4_no_unsafe_policy_rag" and not check.ok for check in report.checks)
