from __future__ import annotations

from types import SimpleNamespace

from scripts.trace_net_h30_engram_critic_repair_v1 import (
    CHECK_ROUTES,
    HINT_ROUTES,
    evaluate_policy_checks,
    execute_policy_repair,
    install_engram_critic_repair,
)


def envelope(**overrides):
    value = {
        "retrieval_tunnels_used": [
            "navigation_exact_source_fallback",
            "direct_source_resolution_v2",
        ],
        "direct_evidence": [],
        "candidate_evidence": [],
        "visual_guidance": [{
            "page_id": "t_p_120_1176_p000084",
            "subject": (
                "visual page associated with part "
                "120-41824-003"
            ),
        }],
        "semantic_guidance": [],
        "authority_evidence": [],
        "contradictions": [],
        "coverage": {
            "navigation_leads": [{
                "page_id": "t_p_120_1176_p000003",
                "source_type": "table",
                "document": (
                    "table_exact_search::"
                    "t_p_120_1176_p000003::covered_part_number::"
                    "ae28c8694c95f9d6"
                ),
                "snippet": "120-41824-003",
            }],
            "ocr_evidence": [],
            "aggregate_records": [],
            "claim_results": {},
            "retrieval_completion": {
                "scanned_file_count": 4,
                "matched_file_count": 2,
                "coverage_complete_for_candidate_files": True,
            },
        },
        "crag_repairs": [],
        "safety_contract": {
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        },
        "upstream_results": [],
    }
    value.update(overrides)
    return SimpleNamespace(**value)


def plan(
    route="document_page_navigation",
    checks=None,
    hints=None,
    budget=2,
):
    return SimpleNamespace(
        primary_route=route,
        repair_budget=budget,
        engram_policy={
            "critic_policy": {
                "checks": list(checks or []),
            },
            "repair_policy": {
                "hints": list(hints or []),
            },
        },
    )


def atoms(
    route="document_page_navigation",
    claims=None,
):
    return SimpleNamespace(
        latest_query=(
            "Which source document and page contain the strongest "
            "evidence for part 120-41824-003?"
        ),
        normalized_query=(
            "which source document and page contain the strongest "
            "evidence for part 120-41824-003?"
        ),
        exact_part_numbers=["120-41824-003"],
        part_prefix=None,
        part_contains=None,
        part_suffix=None,
        nomenclature_terms=[],
        requested_claims=list(
            claims or ["exact_identifier"]
        ),
    )


def base_critic(**overrides):
    value = {
        "quality_status": "PASS",
        "failures": [],
        "warnings": [],
        "retry_required": False,
        "dimensions": {"safety": "PASS"},
    }
    value.update(overrides)
    return value


def test_route_filter_skips_irrelevant_inherited_checks():
    current_plan = plan(
        checks=[
            "top_result_matches_exact_entity",
            "aggregation_coverage_required",
            "claim_buckets_collapsed",
        ],
    )
    result = evaluate_policy_checks(
        current_plan,
        atoms(),
        envelope(),
        base_critic(),
    )
    assert "top_result_matches_exact_entity" in (
        result["policy_checks_executed"]
    )
    skipped = {
        row["check"]
        for row in result["policy_checks_skipped"]
    }
    assert "aggregation_coverage_required" in skipped
    assert "claim_buckets_collapsed" in skipped


def test_internal_identifier_failure_recommends_only_selected_repair():
    current_plan = plan(
        checks=["no_internal_identifier_exposure"],
        hints=[
            "sanitize_internal_ids",
            "expand_aggregation_coverage",
        ],
    )
    result = evaluate_policy_checks(
        current_plan,
        atoms(),
        envelope(),
        base_critic(),
    )
    assert result["policy_failures"] == [
        "no_internal_identifier_exposure"
    ]
    assert result[
        "policy_repair_hints_recommended"
    ] == ["sanitize_internal_ids"]
    assert result["policy_retry_required"] is True


def test_unselected_check_is_not_executed():
    result = evaluate_policy_checks(
        plan(
            checks=["top_result_matches_exact_entity"],
            hints=["rerank_exact_entity"],
        ),
        atoms(),
        envelope(),
        base_critic(),
    )
    assert "no_internal_identifier_exposure" not in (
        result["policy_checks_executed"]
    )
    assert result["policy_failures"] == []


class FakeRuntime:
    def __init__(self):
        self.queries = []

    def add_unified(self, envelope, query, label):
        self.queries.append((query, label))


def passthrough_completion(
    runtime,
    plan,
    atoms,
    envelope,
    critic,
):
    envelope.coverage.setdefault(
        "completion_called",
        0,
    )
    envelope.coverage["completion_called"] += 1


def test_policy_repair_sanitizes_internal_id_and_records_provenance():
    current_plan = plan(
        checks=["no_internal_identifier_exposure"],
        hints=["sanitize_internal_ids"],
    )
    current_envelope = envelope()
    critic = evaluate_policy_checks(
        current_plan,
        atoms(),
        current_envelope,
        base_critic(),
    )
    handled = execute_policy_repair(
        FakeRuntime(),
        current_plan,
        atoms(),
        current_envelope,
        critic,
        original_repair=passthrough_completion,
        router={},
    )
    assert handled is True
    row = current_envelope.coverage[
        "navigation_leads"
    ][0]
    assert "document" not in row
    assert (
        current_envelope.coverage["completion_called"]
        == 1
    )
    assert len(current_envelope.crag_repairs) == 1
    record = current_envelope.crag_repairs[0]
    assert record["repair_hint"] == "sanitize_internal_ids"
    assert record["read_only"] is True
    assert record["source_truth_mutation_allowed"] is False


def test_policy_repair_runs_at_most_once_per_hint_and_budget():
    current_plan = plan(
        checks=["no_internal_identifier_exposure"],
        hints=["sanitize_internal_ids"],
        budget=1,
    )
    current_envelope = envelope()
    critic = evaluate_policy_checks(
        current_plan,
        atoms(),
        current_envelope,
        base_critic(),
    )
    runtime = FakeRuntime()
    assert execute_policy_repair(
        runtime,
        current_plan,
        atoms(),
        current_envelope,
        critic,
        original_repair=passthrough_completion,
        router={},
    )
    assert execute_policy_repair(
        runtime,
        current_plan,
        atoms(),
        current_envelope,
        critic,
        original_repair=passthrough_completion,
        router={},
    )
    assert len(current_envelope.crag_repairs) == 1


def test_base_deterministic_failure_is_preserved():
    result = evaluate_policy_checks(
        plan(
            checks=["guidance_promoted_to_proof"],
            hints=[],
        ),
        atoms(),
        envelope(),
        base_critic(
            quality_status="RETRY",
            failures=["unsafe_contract:answer_permission"],
            retry_required=True,
        ),
    )
    assert "unsafe_contract:answer_permission" in (
        result["failures"]
    )
    assert result["base_retry_required"] is True
    assert result["retry_required"] is True


def test_navigation_policy_check_passes_after_sanitization():
    current_plan = plan(
        checks=[
            "top_result_matches_exact_entity",
            "no_internal_identifier_exposure",
            "direct_source_attempted",
        ],
        hints=["sanitize_internal_ids"],
    )
    current_envelope = envelope()
    first = evaluate_policy_checks(
        current_plan,
        atoms(),
        current_envelope,
        base_critic(),
    )
    assert "no_internal_identifier_exposure" in (
        first["policy_failures"]
    )
    execute_policy_repair(
        FakeRuntime(),
        current_plan,
        atoms(),
        current_envelope,
        first,
        original_repair=passthrough_completion,
        router={},
    )
    second = evaluate_policy_checks(
        current_plan,
        atoms(),
        current_envelope,
        base_critic(),
    )
    assert second["policy_failures"] == []
    assert second["quality_status"] == "PASS"


def test_installer_wraps_runtime_and_health():
    class Runtime:
        def critic(self, plan, atoms, envelope):
            return base_critic()

        def repair(
            self,
            plan,
            atoms,
            envelope,
            critic,
        ):
            return None

        def health(self):
            return {"quality_status": "PASS"}

    router = {
        "CognitiveRuntime": Runtime,
        "valid_identifier_fragment": lambda value: True,
    }
    install_engram_critic_repair(router)
    assert router[
        "_H30_ENGRAM_CRITIC_REPAIR_V1_INSTALLED"
    ] is True
    health = Runtime().health()
    assert health["policy_aware_self_rag"] is True
    assert health["policy_aware_crag"] is True
    assert health["engram_critic_check_count"] == len(
        CHECK_ROUTES
    )
    assert health["engram_repair_hint_count"] == len(
        HINT_ROUTES
    )
