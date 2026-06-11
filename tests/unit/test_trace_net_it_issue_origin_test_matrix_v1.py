from pathlib import Path

from tiff.trace_net_it_issue_origin_test_matrix_v1 import (
    SCENARIOS,
    build_it_issue_origin_test_matrix,
)


def test_scenario_catalog_is_large_and_origin_based() -> None:
    assert len(SCENARIOS) >= 60
    origins = {scenario.origin_category for scenario in SCENARIOS}
    assert len(origins) >= 15
    severities = {scenario.expected_severity for scenario in SCENARIOS}
    assert {"critical", "warning", "review"}.issubset(severities)


def test_build_issue_origin_matrix_detects_all_scenarios(tmp_path: Path) -> None:
    report = build_it_issue_origin_test_matrix(
        output_dir=tmp_path / "matrix",
        min_scenarios=60,
        min_origin_categories=15,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["scenario_count"] >= 60
    assert report["summary"]["origin_category_count"] >= 15
    assert report["summary"]["undetected_scenario_count"] == 0
    assert report["summary"]["detected_scenario_count"] == report["summary"]["scenario_count"]
    assert Path(report["report_path"]).exists()
    assert Path(report["summary"]["synthetic_console_report_path"]).exists()


def test_matrix_has_examples_for_core_trace_net_origins(tmp_path: Path) -> None:
    report = build_it_issue_origin_test_matrix(output_dir=tmp_path / "matrix")
    origins = set(report["origin_coverage"].keys())
    for expected in {
        "source_ingest",
        "ocr_text",
        "table_extraction",
        "visual_diagram",
        "graph_integrity",
        "trust_authority",
        "semantic_vector",
        "retrieval",
        "feedback_memory",
        "answer_gate",
        "incremental_ops",
        "keyword_search",
        "llm_advisory",
        "security_leakage",
    }:
        assert expected in origins
