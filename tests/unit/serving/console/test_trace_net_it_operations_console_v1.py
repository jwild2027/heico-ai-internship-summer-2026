from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_it_operations_console_v1 import build_it_operations_console, check_it_operations_console_quality


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_it_ops_console_passes_with_clean_stage(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    write_json(
        root / "feedback_memory" / "trace_net_feedback_memory_v1_quality.json",
        {
            "status": "PASS",
            "summary": {
                "feedback_event_count": 4,
                "raw_feedback_direct_to_llm_count": 0,
                "feedback_can_answer_directly_count": 0,
                "feedback_can_prove_claims_count": 0,
                "feedback_can_mutate_source_truth_count": 0,
                "prompt_injection_flagged_count": 1,
            },
        },
    )

    report = build_it_operations_console(
        trace_net_root=root,
        output_dir=tmp_path / "out",
        include_all_quality_files=True,
        max_critical_issues=0,
        allow_missing_expected_stages=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["critical_issue_count"] == 0
    assert report["summary"]["review_issue_count"] >= 1
    assert Path(report["report_path"]).exists()
    assert Path(report["html_path"]).exists()


def test_it_ops_console_fails_on_unsafe_count(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    write_json(
        root / "final_answer_gate" / "trace_net_final_answer_gate_v1_quality.json",
        {
            "status": "PASS",
            "summary": {
                "final_claim_count": 7,
                "unsafe_result_count": 1,
                "source_truth_mutation_allowed_count": 0,
            },
        },
    )

    report = build_it_operations_console(
        trace_net_root=root,
        output_dir=tmp_path / "out",
        include_all_quality_files=True,
        max_critical_issues=0,
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["critical_issue_count"] >= 1
    assert any((issue.get("key") or "").endswith("unsafe_result_count") for issue in report["issues"])


def test_quality_check_can_allow_known_critical_for_diagnostics(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    write_json(root / "x" / "bad_quality.json", {"status": "PASS", "unsafe_record_count": 1})
    report = build_it_operations_console(root, tmp_path / "out", max_critical_issues=0)
    quality = check_it_operations_console_quality(Path(report["report_path"]), max_critical_issues=5)
    # The stage itself had no FAIL status, and the caller explicitly allowed diagnostics with critical issues.
    assert quality["status"] == "PASS"


def test_missing_expected_stages_are_warning_by_default(tmp_path: Path) -> None:
    report = build_it_operations_console(
        trace_net_root=tmp_path / "missing_root",
        output_dir=tmp_path / "out",
        include_all_quality_files=False,
        allow_missing_expected_stages=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["missing_expected_stage_count"] > 0
    assert report["summary"]["warning_issue_count"] > 0


def test_missing_expected_stages_can_be_required(tmp_path: Path) -> None:
    report = build_it_operations_console(
        trace_net_root=tmp_path / "missing_root",
        output_dir=tmp_path / "out",
        include_all_quality_files=False,
        allow_missing_expected_stages=False,
    )
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["critical_issue_count"] > 0


def test_it_ops_console_excludes_nested_synthetic_issue_matrix_artifacts_by_default(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    write_json(root / "real_stage" / "real_quality.json", {"status": "PASS", "unsafe_record_count": 0})
    write_json(
        root / "it_issue_origin_test_matrix" / "synthetic_trace_net_root" / "bad" / "bad_quality.json",
        {"status": "PASS", "unsafe_record_count": 99},
    )
    write_json(
        root / "it_issue_origin_test_matrix" / "synthetic_console_report" / "trace_net_it_operations_console_v1_quality.json",
        {"status": "FAIL", "critical_issue_count": 99},
    )

    report = build_it_operations_console(
        trace_net_root=root,
        output_dir=tmp_path / "out",
        include_all_quality_files=True,
        max_critical_issues=0,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["critical_issue_count"] == 0
    assert report["summary"]["stage_fail_count"] == 0
    assert report["summary"]["excluded_quality_file_count"] == 2


def test_it_ops_console_can_include_nested_synthetic_issue_matrix_artifacts_for_diagnostics(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    write_json(
        root / "it_issue_origin_test_matrix" / "synthetic_trace_net_root" / "bad" / "bad_quality.json",
        {"status": "PASS", "unsafe_record_count": 99},
    )

    report = build_it_operations_console(
        trace_net_root=root,
        output_dir=tmp_path / "out",
        include_all_quality_files=True,
        max_critical_issues=0,
        excluded_relative_prefixes=[],
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["critical_issue_count"] >= 1
    assert report["summary"]["excluded_quality_file_count"] == 0


def test_it_ops_console_excludes_its_own_output_directory_by_default(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    output_dir = root / "it_operations_console"
    write_json(root / "real_stage" / "real_quality.json", {"status": "PASS", "unsafe_record_count": 0})
    write_json(
        output_dir / "trace_net_it_operations_console_v1_quality.json",
        {
            "status": "FAIL",
            "summary": {
                "critical_issue_count": 3,
                "raw_feedback_direct_to_llm_issue_count": 1,
                "source_truth_mutation_issue_count": 1,
            },
        },
    )

    report = build_it_operations_console(
        trace_net_root=root,
        output_dir=output_dir,
        include_all_quality_files=True,
        max_critical_issues=0,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["critical_issue_count"] == 0
    assert report["summary"]["stage_fail_count"] == 0
    assert report["summary"]["excluded_quality_file_count"] == 1
    assert ["it_operations_console"] in report["summary"]["excluded_relative_prefixes"]


def test_it_ops_console_can_include_its_output_directory_for_diagnostics(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    output_dir = root / "it_operations_console"
    write_json(
        output_dir / "trace_net_it_operations_console_v1_quality.json",
        {"status": "FAIL", "unsafe_record_count": 1},
    )

    report = build_it_operations_console(
        trace_net_root=root,
        output_dir=output_dir,
        include_all_quality_files=True,
        max_critical_issues=0,
        exclude_output_dir_artifacts=False,
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["critical_issue_count"] >= 1
    assert report["summary"]["excluded_quality_file_count"] == 0
