from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_graph_query_helper_v1 import (
    QualityThresholds,
    build_graph_query_helper,
    check_graph_query_helper_quality,
)

from tests.unit.test_trace_net_graph_query_helper_v1 import sample_graph


def test_quality_checker_passes_built_report(tmp_path: Path) -> None:
    nodes_path, edges_path, dublin_path, leiden_path = sample_graph(tmp_path)
    out_dir = tmp_path / "out"
    build_graph_query_helper(
        graph_nodes_path=nodes_path,
        graph_edges_path=edges_path,
        dublin_core_source_package_extension=dublin_path,
        leiden_navigation_metadata_bridge=leiden_path,
        part_numbers=["120-46137-001"],
        page_ids=["t_p_120_1176_p000003"],
        ata_codes=["25-21-00"],
        output_dir=out_dir,
        thresholds=QualityThresholds(min_query_records=3, min_page_results=3, min_source_resolved_results=3, require_no_answer_permission=True),
        write_quality=True,
    )
    quality = check_graph_query_helper_quality(
        report_path=out_dir / "trace_net_graph_query_helper_v1.json",
        thresholds=QualityThresholds(min_query_records=3, min_page_results=3, min_source_resolved_results=3, require_no_answer_permission=True),
        write_json_report=True,
    )
    assert quality["quality_status"] == "PASS"
    assert quality["summary"]["source_truth_mutation_allowed_count"] == 0
    assert (out_dir / "trace_net_graph_query_helper_v1_quality.json").exists()


def test_quality_checker_fails_minimums(tmp_path: Path) -> None:
    nodes_path, edges_path, dublin_path, leiden_path = sample_graph(tmp_path)
    out_dir = tmp_path / "out"
    build_graph_query_helper(
        graph_nodes_path=nodes_path,
        graph_edges_path=edges_path,
        dublin_core_source_package_extension=dublin_path,
        leiden_navigation_metadata_bridge=leiden_path,
        part_numbers=["120-46137-001"],
        output_dir=out_dir,
        write_quality=True,
    )
    quality = check_graph_query_helper_quality(
        report_path=out_dir / "trace_net_graph_query_helper_v1.json",
        thresholds=QualityThresholds(min_query_records=999),
        write_json_report=False,
    )
    assert quality["quality_status"] == "FAIL"
    assert quality["quality_issues"]


def test_quality_json_has_thresholds(tmp_path: Path) -> None:
    nodes_path, edges_path, dublin_path, leiden_path = sample_graph(tmp_path)
    out_dir = tmp_path / "out"
    build_graph_query_helper(
        graph_nodes_path=nodes_path,
        graph_edges_path=edges_path,
        dublin_core_source_package_extension=dublin_path,
        leiden_navigation_metadata_bridge=leiden_path,
        part_numbers=["120-46137-001"],
        output_dir=out_dir,
        thresholds=QualityThresholds(require_no_answer_permission=True),
        write_quality=True,
    )
    payload = json.loads((out_dir / "trace_net_graph_query_helper_v1_quality.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "trace_net_graph_query_helper_v1_quality"
    assert "thresholds" in payload
    assert "summary" in payload
