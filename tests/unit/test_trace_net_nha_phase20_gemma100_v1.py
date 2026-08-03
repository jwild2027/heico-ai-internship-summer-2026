from __future__ import annotations

import json
from pathlib import Path

from scripts.trace_net_nha_phase5_synthetic_benchmark_v1 import (
    build_answer_key,
    build_synthetic_benchmark,
    validate_phase5,
    build_graph_overlay,
)
from scripts.trace_net_nha_phase20_gemma100_v1 import (
    DIRECT_PARENT_TEMPLATES,
    build_benchmark_packet,
    build_gemma100_answer_key,
    build_gemma100_bank,
    build_synthetic_engine,
    confirmed_relationships,
    evaluate_model_answer,
    execute_case,
    load_phase5_bundle,
    summarize_results,
)
from tiff.trace_net_nha_engram_v1 import (
    build_nha_memory_atoms,
    build_nha_skill_library,
    extract_nha_query_atoms,
)


def inventory(count: int = 100):
    return [
        {
            "source_exists": True,
            "canonical_page_id": f"t_p_synthetic_test_{index:06d}",
            "tiff_filename": f"{index:08d}.tif",
            "page_ordinal": index,
        }
        for index in range(1, count + 1)
    ]


def in_memory_bundle():
    built = build_synthetic_benchmark(inventory())
    answer_key = build_answer_key(built["scenarios"], built["relationships"], built["questions"])
    assignments = built["page_assignments"]
    return {
        "quality_status": "PASS",
        "failures": [],
        "relationships": built["relationships"],
        "assignments": assignments,
        "scenarios": built["scenarios"],
        "source_answer_key": answer_key,
        "assignment_by_relationship": {
            str(row.get("relationship_id") or ""): dict(row)
            for row in assignments
            if str(row.get("relationship_id") or "")
        },
        "sha256": {"source_answer_key": "a" * 64, "relationships": "b" * 64},
    }


def engram_bundle():
    return {
        "quality_status": "PASS",
        "memory_atoms": build_nha_memory_atoms(),
        "skill_cards": build_nha_skill_library()["skill_cards"],
    }


def write_phase5(tmp_path: Path) -> Path:
    built = build_synthetic_benchmark(inventory())
    answer_key = build_answer_key(built["scenarios"], built["relationships"], built["questions"])
    graph = build_graph_overlay(built["scenarios"], built["relationships"], built["page_assignments"])
    quality = validate_phase5(
        inventory(), built["scenarios"], built["relationships"], built["page_assignments"], built["questions"], graph
    )
    payloads = {
        "trace_net_nha_synthetic_relationships_v1.json": {"records": built["relationships"]},
        "trace_net_nha_synthetic_page_assignments_v1.json": {"records": built["page_assignments"]},
        "trace_net_nha_synthetic_scenarios_v1.json": {"records": built["scenarios"]},
        "trace_net_nha_synthetic_answer_key_v1.json": answer_key,
        "trace_net_nha_phase5_quality_v1.json": quality,
    }
    for name, payload in payloads.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def test_phase5_bundle_has_more_than_40_confirmed_relationships():
    rows = confirmed_relationships(in_memory_bundle())
    assert len(rows) >= 40
    assert all(row["assigned_page_id"] for row in rows)


def test_gemma100_bank_is_exactly_100_unique_normal_queries():
    bank = build_gemma100_bank(in_memory_bundle())
    assert len(bank) == 100
    assert len({row["query"] for row in bank}) == 100
    assert len({row["relationship_id"] for row in bank}) >= 40
    assert len({row["template_index"] for row in bank}) >= 20
    assert sum(row["stream"] for row in bank) == 50


def test_all_100_queries_are_recognized_as_direct_nha_language():
    bank = build_gemma100_bank(in_memory_bundle())
    for row in bank:
        atoms = extract_nha_query_atoms(row["query"])
        assert atoms["nha_candidate"] is True
        assert atoms["intent"] == "direct_nha"
        assert atoms["synthetic_blocked"] is True


def test_answer_key_is_derived_from_phase5_synthetic_bundle():
    bundle = in_memory_bundle()
    bank = build_gemma100_bank(bundle)
    key = build_gemma100_answer_key(bank, bundle)
    assert key["case_count"] == 100
    assert key["truth_mode"] == "synthetic_benchmark"
    assert key["production_visible"] is False
    assert key["source_answer_key_sha256"] == "a" * 64


def test_packet_uses_scope_and_expected_direct_parent():
    bundle = in_memory_bundle()
    case = build_gemma100_bank(bundle)[0]
    packet = build_benchmark_packet(case, engine=build_synthetic_engine(bundle), engram_bundle=engram_bundle())
    assert packet["eligible"] is True
    assert packet["intent"] == "direct_nha"
    assert packet["evidence"]["direct_nha"] == case["expected_direct_nha"]
    assert packet["selected_skill_ids"] == ["nha_direct_parent_lookup"]
    assert packet["synthetic_artifact_access_count"] == 1


def test_real_model_call_result_is_scored_against_answer_key():
    bundle = in_memory_bundle()
    case = build_gemma100_bank(bundle)[0]

    def fake_model_call(**kwargs):
        answer = f"The direct NHA of {case['child_part']} is {case['expected_direct_nha']}."
        return {
            "quality_status": "PASS",
            "http_status": 200,
            "content": json.dumps({"answer": answer}),
            "prompt_eval_count": 120,
            "eval_count": 24,
        }

    result = execute_case(
        case,
        engine=build_synthetic_engine(bundle),
        engram_bundle=engram_bundle(),
        model_call=fake_model_call,
    )
    assert result["model_call_count"] == 1
    assert result["writer_source"] == "gemma"
    assert result["gemma_writer_accepted"] is True
    assert result["deterministic_fallback_used"] is False
    assert result["answer_key_pass"] is True


def test_wrong_parent_fails_answer_key_comparison():
    case = {
        "case_id": "NHA-GEMMA100-001",
        "child_part": "990-91001-001",
        "expected_direct_nha": "990-91101-001",
    }
    result = evaluate_model_answer(
        case,
        "The direct NHA of 990-91001-001 is 990-99999-001.",
        model_call_count=1,
        writer_accepted=True,
        prompt_tokens=10,
        completion_tokens=10,
    )
    assert result["passed"] is False
    assert "expected_direct_nha_missing_from_answer" in result["failures"]


def test_summary_requires_all_100_gemma_answers_to_pass():
    bank = build_gemma100_bank(in_memory_bundle())
    results = [
        {
            "case_id": row["case_id"],
            "query": row["query"],
            "passed": True,
            "http_status": 200,
            "answer_key_pass": True,
            "model_call_count": 1,
            "gemma_writer_accepted": True,
            "deterministic_fallback_used": False,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "latency_seconds": 1.0,
            "synthetic_artifact_access_count": 1,
        }
        for row in bank
    ]
    summary = summarize_results(bank, results)
    assert summary["quality_status"] == "PASS"
    assert summary["counts"]["model_call_count"] == 100
    assert summary["counts"]["answer_key_pass_count"] == 100


def test_phase5_loader_enforces_benchmark_isolation(tmp_path):
    root = write_phase5(tmp_path)
    bundle = load_phase5_bundle(root)
    assert bundle["quality_status"] == "PASS"
    assert len(bundle["relationships"]) == 66



def test_tracked_phase5_direct_parent_key_generates_exactly_100_queries():
    key = Path("tests/fixtures/trace_net_nha_phase20_synthetic_direct_parent_answer_key_v1.json")
    bundle = load_phase5_bundle(key)
    assert bundle["quality_status"] == "PASS"
    assert len(bundle["relationships"]) == 50
    bank = build_gemma100_bank(bundle)
    assert len(bank) == 100
    assert len({row["query"] for row in bank}) == 100


def test_direct_parent_template_library_is_diverse():
    assert len(DIRECT_PARENT_TEMPLATES) >= 20
    assert len(set(DIRECT_PARENT_TEMPLATES)) == len(DIRECT_PARENT_TEMPLATES)


def test_launcher_isolates_legacy_tests_from_phase19_env():
    launcher = Path("scripts/launch_trace_net_cognitive_openwebui_v1.sh").read_text(encoding="utf-8")
    assert 'TRACE_NET_H30_PHASE19_PRESERVATION_WRITER_ENABLED=0 "$PYTHON" -m pytest -q' in launcher
