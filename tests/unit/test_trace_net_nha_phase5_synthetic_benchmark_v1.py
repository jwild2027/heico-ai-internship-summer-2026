from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from scripts.trace_net_nha_phase5_synthetic_benchmark_v1 import (
    CASE_COUNTS,
    DEFAULT_SEED,
    EXPECTED_QUESTION_COUNT,
    EXPECTED_SCENARIO_COUNT,
    build_answer_key,
    build_graph_overlay,
    build_phase5,
    build_synthetic_benchmark,
    validate_phase5,
)


def inventory(count: int = 100):
    return [
        {
            "canonical_page_id": f"t_p_120_1176_p{i:06d}",
            "tiff_filename": f"{i:08d}.tif",
            "page_ordinal": i,
            "source_exists": True,
            "truth_mode": "real_source",
            "source_truth": True,
        }
        for i in range(1, count + 1)
    ]


def test_distribution_and_counts_are_exact():
    built = build_synthetic_benchmark(inventory(), seed=DEFAULT_SEED)
    assert len(built["scenarios"]) == EXPECTED_SCENARIO_COUNT == 30
    assert len(built["questions"]) == EXPECTED_QUESTION_COUNT == 60
    assert len(built["relationships"]) == 66
    assert len(built["page_assignments"]) == 68
    assert Counter(row["case_type"] for row in built["scenarios"]) == Counter(CASE_COUNTS)


def test_same_seed_is_deterministic_and_different_seed_changes_pages():
    first = build_synthetic_benchmark(inventory(), seed=DEFAULT_SEED)
    second = build_synthetic_benchmark(inventory(), seed=DEFAULT_SEED)
    other = build_synthetic_benchmark(inventory(), seed="ANOTHER-SEED")
    assert first == second
    assert [row["page_id"] for row in first["page_assignments"]] != [row["page_id"] for row in other["page_assignments"]]


def test_all_assignments_are_unique_valid_and_non_mutating():
    pages = inventory()
    built = build_synthetic_benchmark(pages)
    valid = {row["canonical_page_id"] for row in pages}
    assigned = [row["page_id"] for row in built["page_assignments"]]
    assert len(assigned) == len(set(assigned))
    assert set(assigned) <= valid
    assert all(not row["physical_tiff_modified"] and not row["ocr_source_modified"] for row in built["page_assignments"])
    assert all(row["truth_mode"] == "synthetic_benchmark" and row["production_visible"] is False for row in built["page_assignments"])


def test_three_hop_case_preserves_direct_parent_and_order():
    built = build_synthetic_benchmark(inventory())
    scenario = next(row for row in built["scenarios"] if row["case_type"] == "three_hop_chain")
    scoped = sorted((row for row in built["relationships"] if row["scenario_id"] == scenario["scenario_id"]), key=lambda row: row["hop_index"])
    chain = scenario["expected_relationship_order"]
    assert [row["child_part"] for row in scoped] == chain[:-1]
    assert [row["direct_nha"] for row in scoped] == chain[1:]
    question = next(row for row in built["questions"] if row["scenario_id"] == scenario["scenario_id"] and row["category"] == "direct_nha")
    assert question["expected_direct_nha"] == chain[1]
    assert chain[-1] != question["expected_direct_nha"]


def test_project_and_revision_scoping_are_explicit():
    built = build_synthetic_benchmark(inventory())
    project_case = next(row for row in built["scenarios"] if row["case_type"] == "same_child_two_projects")
    project_relationships = [row for row in built["relationships"] if row["scenario_id"] == project_case["scenario_id"]]
    assert len({row["project_id"] for row in project_relationships}) == 2
    assert len({row["direct_nha"] for row in project_relationships}) == 2
    revision_case = next(row for row in built["scenarios"] if row["case_type"] == "revision_change")
    revision_relationships = [row for row in built["relationships"] if row["scenario_id"] == revision_case["scenario_id"]]
    assert len({row["revision_id"] for row in revision_relationships}) == 2
    assert len({row["direct_nha"] for row in revision_relationships}) == 2


def test_contradiction_and_no_nha_fail_closed():
    built = build_synthetic_benchmark(inventory())
    contradiction = next(row for row in built["scenarios"] if row["case_type"] == "contradiction")
    conflict_rows = [row for row in built["relationships"] if row["scenario_id"] == contradiction["scenario_id"]]
    assert len(conflict_rows) == 2
    assert all(row["benchmark_truth_status"] == "conflict" and not row["direct_nha"] for row in conflict_rows)
    no_nha_ids = {row["scenario_id"] for row in built["scenarios"] if row["case_type"] == "no_nha"}
    assert not any(row["scenario_id"] in no_nha_ids for row in built["relationships"])


def test_graph_uses_only_benchmark_prefixed_edges():
    built = build_synthetic_benchmark(inventory())
    graph = build_graph_overlay(built["scenarios"], built["relationships"], built["page_assignments"])
    assert graph["overlay_enabled_by_default"] is False
    assert graph["production_graph_compatible"] is False
    assert graph["edges"]
    assert all(row["edge_type"].startswith("BENCHMARK_") for row in graph["edges"])
    assert all(row["properties"]["production_visible"] is False for row in graph["nodes"])


def test_answer_key_covers_every_question():
    built = build_synthetic_benchmark(inventory())
    answer_key = build_answer_key(built["scenarios"], built["relationships"], built["questions"])
    assert answer_key["case_count"] == EXPECTED_QUESTION_COUNT
    assert {row["question_id"] for row in answer_key["cases"]} == {row["question_id"] for row in built["questions"]}


def test_validator_passes_and_rejects_visibility_leak():
    pages = inventory()
    built = build_synthetic_benchmark(pages)
    graph = build_graph_overlay(built["scenarios"], built["relationships"], built["page_assignments"])
    result = validate_phase5(pages, built["scenarios"], built["relationships"], built["page_assignments"], built["questions"], graph)
    assert result["quality_status"] == "PASS", result
    broken = [dict(row) for row in built["page_assignments"]]
    broken[0]["production_visible"] = True
    result = validate_phase5(pages, built["scenarios"], built["relationships"], broken, built["questions"], graph)
    assert result["quality_status"] == "FAIL"
    assert "synthetic_record_visibility_contract_invalid" in result["failures"]


def test_end_to_end_build_and_cli_entrypoints(tmp_path):
    phase0 = tmp_path / "n0"
    phase4 = tmp_path / "n4"
    output = tmp_path / "n5"
    phase0.mkdir()
    phase4.mkdir()
    (phase0 / "trace_net_nha_page_inventory_v1.json").write_text(json.dumps({"records": inventory()}), encoding="utf-8")
    (phase4 / "trace_net_nha_hierarchy_relationships_v1.json").write_text(json.dumps({"records": [{"relationship_id": "real-r1"}]}), encoding="utf-8")
    (phase4 / "trace_net_nha_phase4_quality_v1.json").write_text(json.dumps({"quality_status": "PASS"}), encoding="utf-8")
    summary = build_phase5(phase0_3_dir=phase0, phase4_dir=phase4, output_dir=output)
    assert summary["quality_status"] == "PASS"
    assert (output / "trace_net_nha_synthetic_answer_key_v1.json").exists()
    assert (output / "trace_net_nha_phase5_summary_v1.json").exists()

    repo_root = Path(__file__).resolve().parents[2]
    for relative in (
        "scripts/build_trace_net_nha_phase5_synthetic_benchmark_v1.py",
        "scripts/check_trace_net_nha_phase5_synthetic_benchmark_v1.py",
    ):
        completed = subprocess.run([sys.executable, "-B", str(repo_root / relative), "--help"], cwd=tmp_path, text=True, capture_output=True, check=False)
        assert completed.returncode == 0, completed.stderr
        assert "usage:" in completed.stdout.lower()
