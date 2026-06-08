from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiff import trace_net_ask_hybrid_flag_v1 as mod


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def regression_payload(status: str = "PASS") -> dict:
    return {
        "schema_version": "trace_net_regression_eval_v1",
        "status": status,
        "quality": {"status": status},
        "summary": {
            "case_fail_count": 0 if status == "PASS" else 1,
            "required_case_missing_count": 0,
            "case_unsafe_result_count": 0,
            "case_direct_answer_allowed_count": 0,
            "case_claim_proof_allowed_count": 0,
            "case_source_truth_mutation_allowed_count": 0,
            "candidate_collection_count": 1476,
            "page_profile_collection_count": 509,
            "embedding_dim": 1024,
        },
    }


def hybrid_payload() -> dict:
    group = {
        "rank": 1,
        "page_id": "t_p_120_1176_p000001",
        "hybrid_score": 1.23,
        "retrieval_safe": True,
        "answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "page_profile_hit_count": 1,
        "candidate_hit_count": 2,
        "trace_resolved_hit_count": 3,
        "citation_present_hit_count": 2,
        "candidate_buckets": {"source_text_evidence": 2},
        "authorities": ["source_text_evidence"],
        "trust_tiers": ["B"],
        "unsafe_reasons": [],
    }
    return {
        "schema_version": "trace_net_hybrid_retrieval_sim_v1",
        "status": "SIM_RAN",
        "quality_status": "PASS",
        "report_path": "local_data/organization/trace_net/ask_hybrid_flag/hybrid_runtime/trace_net_hybrid_retrieval_sim_v1.json",
        "summary": {
            "candidate_collection_count": 1476,
            "page_profile_collection_count": 509,
            "embedding_mode": "ollama",
            "embedding_model_name": "bge-m3:latest",
            "embedding_dim": 1024,
        },
        "query_results": [
            {
                "query_id": "inline_001",
                "query": "manual revision history",
                "ranked_groups": [group],
            }
        ],
    }


def test_run_hybrid_flag_writes_safe_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    regression_path = tmp_path / "regression.json"
    write_json(regression_path, regression_payload())
    monkeypatch.setattr(mod, "run_hybrid_retrieval_sim", lambda **kwargs: hybrid_payload())

    report = mod.run_trace_net_ask_hybrid_flag(
        query="manual revision history",
        retrieval_mode="hybrid-simulate",
        regression_report_path=regression_path,
        output_dir=tmp_path / "ask",
        write_quality=True,
    )

    assert report["status"] == "ASK_RAN"
    assert report["quality_status"] == "PASS"
    assert report["summary"]["retrieval_mode"] == "hybrid-simulate"
    assert report["summary"]["answer_status"] == "NOT_COMPOSED_SIMULATION_ONLY"
    assert report["summary"]["direct_answer_allowed_group_count"] == 0
    assert report["summary"]["claim_proof_allowed_group_count"] == 0
    assert report["summary"]["source_truth_mutation_allowed_group_count"] == 0
    assert Path(report["report_path"]).exists()
    assert Path(report["markdown_path"]).exists()


def test_regression_gate_blocks_failed_regression(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    regression_path = tmp_path / "regression.json"
    write_json(regression_path, regression_payload("FAIL"))
    monkeypatch.setattr(mod, "run_hybrid_retrieval_sim", lambda **kwargs: hybrid_payload())

    with pytest.raises(mod.AskHybridFlagError):
        mod.run_trace_net_ask_hybrid_flag(
            query="manual revision history",
            retrieval_mode="hybrid-simulate",
            regression_report_path=regression_path,
            output_dir=tmp_path / "ask",
        )


def test_off_mode_does_not_run_hybrid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    regression_path = tmp_path / "regression.json"
    write_json(regression_path, regression_payload())

    def fail_if_called(**kwargs):  # pragma: no cover - should not be called
        raise AssertionError("hybrid should not run when flag is off")

    monkeypatch.setattr(mod, "run_hybrid_retrieval_sim", fail_if_called)
    report = mod.run_trace_net_ask_hybrid_flag(
        query="manual revision history",
        retrieval_mode="off",
        regression_report_path=regression_path,
        output_dir=tmp_path / "ask",
    )
    assert report["status"] == "FLAG_OFF"
    assert report["summary"]["retrieval_mode"] == "off"
    assert report["summary"]["hybrid_quality_status"] == "NOT_RUN"


def test_effective_query_prefers_part_then_page_then_query() -> None:
    assert mod.effective_query(query="x", page_id="p1", part_number="PN") == "PN"
    assert mod.effective_query(query="x", page_id="p1") == "p1"
    assert mod.effective_query(query="x") == "x"


def test_load_regression_status_detects_safe_payload(tmp_path: Path) -> None:
    path = tmp_path / "regression.json"
    write_json(path, regression_payload())
    status = mod.load_regression_status(path)
    assert status["quality_status"] == "PASS"
    assert status["safe"] is True


def test_hybrid_flag_passes_current_step7_keyword_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    regression_path = tmp_path / "regression.json"
    write_json(regression_path, regression_payload())
    captured = {}

    def fake_hybrid(**kwargs):
        captured.update(kwargs)
        return hybrid_payload()

    monkeypatch.setattr(mod, "run_hybrid_retrieval_sim", fake_hybrid)
    report = mod.run_trace_net_ask_hybrid_flag(
        query="manual revision history",
        retrieval_mode="hybrid-simulate",
        regression_report_path=regression_path,
        output_dir=tmp_path / "ask",
        database_url="postgresql://unused:unused@localhost:5432/unused",
        max_groups=3,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
    )

    assert report["quality_status"] == "PASS"
    assert "database_url" not in captured
    assert "max_groups_per_query" not in captured
    assert "min_ranked_groups" not in captured
    assert "min_unique_group_pages" not in captured
    assert captured["max_groups"] == 3
    assert captured["min_grouped_results"] == 1
    assert captured["min_resolved_candidate_hits"] == 1
    assert captured["min_resolved_page_profile_hits"] == 1


def test_run_hybrid_flag_accepts_released_step7_results_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    regression_path = tmp_path / "regression.json"
    write_json(regression_path, regression_payload())
    base = hybrid_payload()
    released_shape = {
        "schema_version": "trace_net_hybrid_retrieval_sim_v1",
        "status": "PASS",
        "quality": {"status": "PASS", "checks": []},
        "summary": base["summary"],
        "results": base["query_results"],
        "report_path": "local_data/organization/trace_net/ask_hybrid_flag/hybrid_runtime/trace_net_hybrid_retrieval_sim_v1.json",
    }
    monkeypatch.setattr(mod, "run_hybrid_retrieval_sim", lambda **kwargs: released_shape)

    report = mod.run_trace_net_ask_hybrid_flag(
        query="manual revision history",
        retrieval_mode="hybrid-simulate",
        regression_report_path=regression_path,
        output_dir=tmp_path / "ask",
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["hybrid_quality_status"] == "PASS"
    assert report["summary"]["ranked_group_count"] == 1
    assert report["summary"]["safe_group_count"] == 1
    assert report["top_groups"][0]["page_id"] == "t_p_120_1176_p000001"


def test_run_hybrid_flag_loads_step7_report_path_result_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    regression_path = tmp_path / "regression.json"
    write_json(regression_path, regression_payload())
    full_report_path = tmp_path / "ask" / "hybrid_runtime" / "trace_net_hybrid_retrieval_sim_v1.json"
    full_report = hybrid_payload()
    full_report.pop("query_results")
    full_report["status"] = "PASS"
    full_report["quality"] = {"status": "PASS", "checks": []}
    full_report["results"] = [
        {
            "query_id": "inline_001",
            "query": "manual revision history",
            "ranked_groups": [
                {
                    "rank": 1,
                    "page_id": "t_p_120_1176_p000004",
                    "page_number": 4,
                    "document_id": "t_p_120_1176",
                    "hybrid_score": 1.5,
                    "safety_status": "retrieval_safe",
                    "answer_allowed": False,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "can_mutate_source_truth": False,
                    "requires_source_resolution": True,
                    "requires_citation": True,
                    "requires_authority_gate": True,
                    "page_profile_hit_count": 1,
                    "candidate_hit_count": 1,
                    "bucket_counts": {"source_text_evidence": 1},
                    "authority_counts": {"source_text_evidence": 1},
                    "trust_tier_counts": {"B": 1},
                    "unsafe_reasons": [],
                }
            ],
        }
    ]
    write_json(full_report_path, full_report)

    def fake_hybrid(**kwargs):
        return {
            "status": "PASS",
            "report_path": str(full_report_path),
            "summary": full_report["summary"],
            "quality": {"status": "PASS", "checks": []},
        }

    monkeypatch.setattr(mod, "run_hybrid_retrieval_sim", fake_hybrid)
    report = mod.run_trace_net_ask_hybrid_flag(
        query="manual revision history",
        retrieval_mode="hybrid-simulate",
        regression_report_path=regression_path,
        output_dir=tmp_path / "ask",
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["hybrid_quality_status"] == "PASS"
    assert report["summary"]["ranked_group_count"] == 1
    assert report["summary"]["safe_group_count"] == 1
    assert report["top_groups"][0]["page_id"] == "t_p_120_1176_p000004"
    assert report["top_groups"][0]["safety_status"] == "retrieval_safe"


def test_run_hybrid_flag_hydrates_compact_step7_return_from_report_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    regression_path = tmp_path / "regression.json"
    write_json(regression_path, regression_payload())
    base = hybrid_payload()
    full_report_path = tmp_path / "hybrid_runtime" / "trace_net_hybrid_retrieval_sim_v1.json"
    full_report = {
        "schema_version": "trace_net_hybrid_retrieval_sim_v1",
        "status": "PASS",
        "quality": {"status": "PASS", "checks": []},
        "summary": base["summary"],
        "results": base["query_results"],
    }
    write_json(full_report_path, full_report)

    compact_return = {
        "status": "PASS",
        "report_path": str(full_report_path),
        "summary": base["summary"],
        "quality": {"status": "PASS", "checks": []},
    }
    monkeypatch.setattr(mod, "run_hybrid_retrieval_sim", lambda **kwargs: compact_return)

    report = mod.run_trace_net_ask_hybrid_flag(
        query="manual revision history",
        retrieval_mode="hybrid-simulate",
        regression_report_path=regression_path,
        output_dir=tmp_path / "ask",
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["hybrid_quality_status"] == "PASS"
    assert report["summary"]["ranked_group_count"] == 1
    assert report["summary"]["safe_group_count"] == 1
    assert report["top_groups"][0]["page_id"] == "t_p_120_1176_p000001"


def test_run_hybrid_flag_prefers_in_memory_results_over_stale_report_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    regression_path = tmp_path / "regression.json"
    write_json(regression_path, regression_payload())

    base = hybrid_payload()
    stale_report_path = tmp_path / "stale" / "trace_net_hybrid_retrieval_sim_v1.json"
    stale_group = dict(base["query_results"][0]["ranked_groups"][0])
    stale_groups = []
    for idx in range(8):
        group = dict(stale_group)
        group["rank"] = idx + 1
        group["page_id"] = f"t_p_120_1176_p{idx + 2:06d}"
        stale_groups.append(group)
    write_json(
        stale_report_path,
        {
            "schema_version": "trace_net_hybrid_retrieval_sim_v1",
            "status": "PASS",
            "quality": {"status": "PASS", "checks": []},
            "summary": base["summary"],
            "results": [
                {
                    "query_id": "stale",
                    "query": "stale query",
                    "ranked_groups": stale_groups,
                }
            ],
        },
    )

    released_shape = {
        "schema_version": "trace_net_hybrid_retrieval_sim_v1",
        "status": "PASS",
        "quality": {"status": "PASS", "checks": []},
        "summary": base["summary"],
        "results": base["query_results"],
        "report_path": str(stale_report_path),
    }
    monkeypatch.setattr(mod, "run_hybrid_retrieval_sim", lambda **kwargs: released_shape)

    report = mod.run_trace_net_ask_hybrid_flag(
        query="manual revision history",
        retrieval_mode="hybrid-simulate",
        regression_report_path=regression_path,
        output_dir=tmp_path / "ask",
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["ranked_group_count"] == 1
    assert report["top_groups"][0]["page_id"] == "t_p_120_1176_p000001"
