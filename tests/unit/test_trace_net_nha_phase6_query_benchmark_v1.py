from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.trace_net.graph.trace_net_nha_phase6_query_benchmark_v1 import (
    NHAQueryEngine,
    build_real_smoke_cases,
    evaluate_synthetic_question,
    render_public_answer,
    validate_phase6,
)


def syn(child: str, parent: str, *, scenario="S1", page="p1", item="10", hop=1, project="P1", config="C1", revision="R1", status="confirmed", candidates=None):
    return {
        "relationship_id": f"r:{child}:{parent}:{project}:{revision}:{item}",
        "scenario_id": scenario,
        "truth_mode": "synthetic_benchmark",
        "child_part": child,
        "direct_nha": parent if status == "confirmed" else "",
        "parent_candidates": list(candidates or ([parent] if parent else [])),
        "project_id": project,
        "configuration_id": config,
        "revision_id": revision,
        "item_number": item,
        "quantity": "1",
        "hop_index": hop,
        "benchmark_truth_status": status,
        "assigned_page_id": page,
    }


def real(child: str, parent: str, *, page="rp1", status="source_supported", candidates=None, depth=1):
    return {
        "relationship_id": f"rr:{child}:{parent}",
        "truth_mode": "real_source",
        "child_part": child,
        "direct_nha": parent if status == "source_supported" else "",
        "parent_candidates": list(candidates or ([parent] if parent else [])),
        "relationship_status": status,
        "hierarchy_depth": depth,
        "row_page_id": page,
        "anchor_page_ids": [page],
        "item_number": "10",
    }


def test_synthetic_engine_requires_explicit_enable():
    with pytest.raises(PermissionError):
        NHAQueryEngine([], truth_mode="synthetic_benchmark")


def test_direct_nha_and_scope_filtering():
    child = "990-95001-001"
    rows = [
        syn(child, "990-95002-001", project="SYN-PROJECT-19A", config="SYN-CONFIG-19A", page="p1"),
        syn(child, "990-95003-001", project="SYN-PROJECT-19B", config="SYN-CONFIG-19B", page="p2"),
    ]
    engine = NHAQueryEngine(rows, truth_mode="synthetic_benchmark", synthetic_enabled=True)
    scoped = engine.direct_nha(child, {"project_id": "SYN-PROJECT-19A"})
    assert scoped["behavior"] == "direct_answer"
    assert scoped["direct_nha"] == "990-95002-001"
    unscoped = engine.direct_nha(child)
    assert unscoped["behavior"] == "candidate_or_clarification"
    assert unscoped["direct_nha"] == ""


def test_ordered_chain_and_pages_follow_hops():
    rows = [
        syn("990-92001-001", "990-92002-001", page="p1", item="10", hop=1),
        syn("990-92002-001", "990-92003-001", page="p2", item="20", hop=2),
        syn("990-92003-001", "990-92004-001", page="p3", item="30", hop=3),
    ]
    engine = NHAQueryEngine(rows, truth_mode="synthetic_benchmark", synthetic_enabled=True)
    result = engine.ancestor_chain("990-92001-001")
    assert result["behavior"] == "ordered_chain_answer"
    assert result["chain"] == ["990-92001-001", "990-92002-001", "990-92003-001", "990-92004-001"]
    assert result["pages"] == ["p1", "p2", "p3"]
    assert result["item_order"] == ["10", "20", "30"]


def test_direct_children_and_descendants_do_not_flatten():
    rows = [
        syn("990-94002-001", "990-94001-001", page="p1", item="10", hop=1),
        syn("990-94003-001", "990-94002-001", page="p2", item="20", hop=2),
        syn("990-94004-001", "990-94003-001", page="p3", item="30", hop=3),
    ]
    engine = NHAQueryEngine(rows, truth_mode="synthetic_benchmark", synthetic_enabled=True)
    direct = engine.direct_children("990-94001-001")
    assert direct["direct_children"] == ["990-94002-001"]
    tree = engine.descendants("990-94001-001")
    assert tree["direct_children"] == ["990-94002-001"]
    assert tree["descendants"] == ["990-94003-001", "990-94004-001"]
    assert tree["chain"] == ["990-94004-001", "990-94003-001", "990-94002-001", "990-94001-001"]


def test_conflict_and_no_nha_fail_closed():
    conflict_rows = [
        syn("990-98001-001", "990-98002-001", status="conflict", candidates=["990-98002-001", "990-98003-001"], page="p1"),
        syn("990-98001-001", "990-98003-001", status="conflict", candidates=["990-98002-001", "990-98003-001"], page="p2", item="20"),
    ]
    engine = NHAQueryEngine(conflict_rows, truth_mode="synthetic_benchmark", synthetic_enabled=True)
    result = engine.direct_nha("990-98001-001")
    assert result["behavior"] == "conflict_limited"
    assert result["direct_nha"] == ""
    assert result["parent_candidates"] == ["990-98002-001", "990-98003-001"]

    scenario = {"scenario_id": "SYN-NHA-029", "isolated_part": "990-99001-001"}
    assignment = {"scenario_id": "SYN-NHA-029", "relationship_id": "", "page_id": "p9"}
    isolated = NHAQueryEngine([], truth_mode="synthetic_benchmark", assignments=[assignment], scenarios=[scenario], synthetic_enabled=True)
    no_nha = isolated.direct_nha("990-99001-001")
    assert no_nha["behavior"] == "no_relationship"
    assert no_nha["pages"] == ["p9"]


def test_question_execution_and_exact_evaluation():
    row = syn("990-91001-001", "990-91101-001", page="p1")
    engine = NHAQueryEngine([row], truth_mode="synthetic_benchmark", synthetic_enabled=True)
    question = {
        "question_id": "Q1",
        "scenario_id": "S1",
        "category": "direct_nha",
        "query": "What is the direct NHA of synthetic part 990-91001-001?",
        "expected_behavior": "direct_answer",
        "expected_direct_nha": "990-91101-001",
        "expected_chain": [],
        "expected_direct_children": [],
        "expected_parent_candidates": [],
        "expected_pages": ["p1"],
        "expected_item_order": [],
    }
    result = engine.execute_question(question)
    evaluation = evaluate_synthetic_question(question, result)
    assert evaluation["passed"] is True
    assert "Synthetic benchmark only" in result["public_answer"]
    assert "physical TIFF and OCR were not modified" in result["public_answer"]


def test_real_smoke_supported_and_ambiguous():
    engine = NHAQueryEngine([
        real("120-1-001", "120-2-001"),
        real("120-3-001", "", status="ambiguous", candidates=["120-4-001", "120-5-001"]),
    ], truth_mode="real_source")
    direct = engine.direct_nha("120-1-001")
    assert direct["behavior"] == "direct_answer"
    limited = engine.direct_nha("120-3-001")
    assert limited["behavior"] == "conflict_limited"
    assert limited["direct_nha"] == ""
    assert "Synthetic benchmark only" not in render_public_answer(direct, synthetic=False)


def test_build_real_smoke_cases_balances_supported_and_limited():
    cases = [
        {"case_id": f"s{i}", "child_part": f"A{i}", "expected_behavior": "direct_answer", "expected_hierarchy_depth": 1}
        for i in range(20)
    ] + [
        {"case_id": f"a{i}", "child_part": f"Z{i}", "expected_behavior": "candidate_or_clarification", "expected_hierarchy_depth": 1}
        for i in range(8)
    ]
    # Duplicate source-backed parents for one child become a context-required
    # limited case rather than an arbitrary positive answer.
    cases.extend([
        {"case_id": "d1", "child_part": "DUP", "expected_behavior": "direct_answer", "expected_direct_nha": "P1", "expected_pages": ["p1"], "expected_hierarchy_depth": 1},
        {"case_id": "d2", "child_part": "DUP", "expected_behavior": "direct_answer", "expected_direct_nha": "P2", "expected_pages": ["p2"], "expected_hierarchy_depth": 1},
    ])
    selected = build_real_smoke_cases(cases, maximum=20)
    assert len(selected) == 20
    assert sum(row["expected_behavior"] != "direct_answer" for row in selected) == 5
    assert not any(row.get("child_part") == "DUP" and row.get("expected_behavior") == "direct_answer" for row in selected)



def test_real_smoke_mixed_supported_and_ambiguous_child_is_only_limited():
    cases = [
        {
            "case_id": "supported",
            "child_part": "120-29073-001",
            "expected_behavior": "direct_answer",
            "expected_direct_nha": "120-29067-001",
            "expected_parent_candidates": ["120-29067-001"],
            "expected_pages": ["p-supported"],
            "expected_hierarchy_depth": 1,
        },
        {
            "case_id": "ambiguous",
            "child_part": "120-29073-001",
            "expected_behavior": "candidate_or_clarification",
            "expected_direct_nha": "",
            "expected_parent_candidates": [
                "120-29067-003",
                "120-29067-021",
                "120-29067-031",
            ],
            "expected_pages": ["p-ambiguous"],
            "expected_hierarchy_depth": 1,
        },
    ]
    selected = build_real_smoke_cases(cases, maximum=1)
    assert len(selected) == 1
    row = selected[0]
    assert row["expected_behavior"] == "candidate_or_clarification"
    assert row["expected_direct_nha"] == ""
    assert row["expected_parent_candidates"] == [
        "120-29067-001",
        "120-29067-003",
        "120-29067-021",
        "120-29067-031",
    ]
    assert set(row["expected_pages"]) == {"p-supported", "p-ambiguous"}


def test_validation_contract_pass_and_fail():
    synthetic = [{"passed": True, "result": {"truth_mode": "synthetic_benchmark", "production_graph_write_count": 0}}]
    real_rows = [{"passed": True, "result": {"truth_mode": "real_source", "production_graph_write_count": 0}}]
    passed = validate_phase6(synthetic, real_rows, expected_synthetic_questions=1, expected_real_questions=1)
    assert passed["quality_status"] == "PASS"
    failed = validate_phase6([{**synthetic[0], "passed": False}], real_rows, expected_synthetic_questions=1, expected_real_questions=1)
    assert failed["quality_status"] == "FAIL"


def test_cli_entrypoints_bootstrap_repo_root(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    for relative in (
        "scripts/benchmark/run_trace_net_nha_phase6_query_benchmark_v1.py",
        "scripts/benchmark/check_trace_net_nha_phase6_query_benchmark_v1.py",
    ):
        completed = subprocess.run(
            [sys.executable, "-B", str(repo_root / relative), "--help"],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "usage:" in completed.stdout.lower()
