from __future__ import annotations

from types import SimpleNamespace

from scripts.trace_net_h30_phase4_3_1_exact_identifier_v1 import (
    build_planner_seed,
    classify_identifier_entity,
    enforce_final_identifier_filter,
    expected_h30_routes,
    explicit_part_partial_wording,
    general_source_overview_requested,
    infer_exact_identifier_candidate,
    looks_identifier_shaped,
    part_fragment_is_explicit,
    phase4_3_1_health,
    validate_planner_proposal,
)


def test_bare_alphanumeric_vs4956_is_exact_part_candidate():
    assert infer_exact_identifier_candidate("Find VS4956") == "VS4956"


def test_bare_alphanumeric_e075221_is_exact_part_candidate():
    assert infer_exact_identifier_candidate("Locate E075221") == "E075221"


def test_one_character_hyphen_segment_is_preserved():
    assert looks_identifier_shaped("1002-F") is True
    assert infer_exact_identifier_candidate("Search for 1002-F") == "1002-F"


def test_standalone_alphanumeric_identifier_is_exact():
    assert infer_exact_identifier_candidate("VS4956") == "VS4956"


def test_where_does_alphanumeric_identifier_is_exact():
    assert infer_exact_identifier_candidate("Where does E075221 appear?") == "E075221"


def test_explicit_part_context_can_preserve_unusual_identifier():
    assert infer_exact_identifier_candidate("Find part n25-IPL") == "N25-IPL"


def test_document_label_is_not_reclassified_as_part():
    assert classify_identifier_entity("Find manual n25-IPL", "n25-IPL") == "document_reference"
    assert infer_exact_identifier_candidate(
        "Find manual n25-IPL", legacy_identifier="n25-IPL"
    ) is None


def test_ata_code_is_not_reclassified_as_part():
    atoms = SimpleNamespace(ata_prefix="25", ata_exact=["25-21-00"])
    assert classify_identifier_entity("Find ATA 25-21-00", "25-21-00", atoms) == "ata_reference"
    assert infer_exact_identifier_candidate(
        "Find ATA 25-21-00", atoms, legacy_identifier="25-21-00"
    ) is None


def test_figure_identifier_is_not_reclassified_as_part():
    assert classify_identifier_entity("Find figure 1002-F", "1002-F") == "figure_reference"


def test_page_identifier_is_not_reclassified_as_part():
    assert classify_identifier_entity("Locate page E075221", "E075221") == "page_reference"


def test_table_contains_part_keeps_part_identity():
    query = "Which table contains 120-41824-003?"
    assert classify_identifier_entity(query, "120-41824-003") == "part_number"
    assert infer_exact_identifier_candidate(
        query, legacy_identifier="120-41824-003"
    ) == "120-41824-003"


def test_table_contains_is_not_partial_part_wording():
    assert explicit_part_partial_wording("Which table contains 120-41824-003?") is False


def test_part_contains_is_explicit_partial_wording():
    query = "The part number contains 50645 somewhere"
    assert explicit_part_partial_wording(query) is True
    assert part_fragment_is_explicit(query, "50645", "contains") is True


def test_ocr_include_request_does_not_demote_exact_part_to_partial():
    query = (
        "Recover the OCR labels for part 120-41824-003 from the blurry scan. "
        "Include the page, OCR engine, confidence, and readable text."
    )
    assert explicit_part_partial_wording(query) is False
    assert infer_exact_identifier_candidate(query) == "120-41824-003"


def test_partial_wording_prevents_exact_promotion():
    assert infer_exact_identifier_candidate("I only remember part VS4956") is None


def test_general_manual_overview_is_semantic_intent():
    assert general_source_overview_requested("Describe the manual at a high level") is True


def test_general_document_structure_is_semantic_intent():
    assert general_source_overview_requested("Tell me about the document structure") is True


def test_general_evidence_types_is_semantic_intent():
    assert general_source_overview_requested("What evidence types does TRACE-Net have?") is True


def test_unrelated_general_sentence_is_not_manual_overview():
    assert general_source_overview_requested("Can you help me with this?") is False


def test_final_filter_removes_post_repair_unrelated_candidates():
    envelope = SimpleNamespace(
        candidate_evidence=[
            {"candidate_value": "VS4956"},
            {"candidate_value": "120-50645-005"},
        ],
        direct_evidence=[
            {"field_name": "part_number", "value": "VS4956"},
            {"field_name": "part_number", "value": "120-50645-005"},
        ],
        coverage={},
        safety_contract={},
    )
    summary = enforce_final_identifier_filter(
        envelope,
        {"identifier_mode": "exact", "normalized_identifier": "VS4956"},
    )
    assert [row["candidate_value"] for row in envelope.candidate_evidence] == ["VS4956"]
    assert [row["value"] for row in envelope.direct_evidence] == ["VS4956"]
    assert summary["candidate_drop_count"] == 1
    assert summary["direct_drop_count"] == 1


def test_final_filter_reasserts_candidate_and_safety_flags():
    envelope = SimpleNamespace(
        # Page-backed so the candidate survives the query-echo guard; the point
        # of this test is safety-flag reassertion on a kept candidate.
        candidate_evidence=[{"candidate_value": "VS4956", "page_id": "t_p_demo_p1"}],
        direct_evidence=[],
        coverage={},
        safety_contract={"answer_permission": True},
    )
    enforce_final_identifier_filter(
        envelope,
        {"identifier_mode": "exact", "normalized_identifier": "VS4956"},
    )
    row = envelope.candidate_evidence[0]
    assert row["guidance_only"] is True
    assert row["source_truth"] is False
    assert row["final_answer_allowed"] is False
    assert envelope.safety_contract["answer_permission"] is False
    assert envelope.safety_contract["source_truth_mutation_allowed"] is False


def test_final_filter_drops_unbacked_query_echo():
    # Negative-control fabrication: a candidate equal to the requested identifier
    # with no direct support and no concrete source page is a query echo.
    envelope = SimpleNamespace(
        candidate_evidence=[{"candidate_value": "999-99999-999", "page_id": "unknown"}],
        direct_evidence=[],
        coverage={},
        safety_contract={},
    )
    summary = enforce_final_identifier_filter(
        envelope,
        {"identifier_mode": "exact", "normalized_identifier": "99999999999"},
    )
    assert envelope.candidate_evidence == []
    assert summary["query_echo_drop_count"] == 1


def test_final_filter_keeps_exact_candidate_backed_by_direct_evidence():
    envelope = SimpleNamespace(
        candidate_evidence=[{"candidate_value": "120-20970-001", "page_id": "unknown"}],
        direct_evidence=[{"field_name": "part_number", "value": "120-20970-001"}],
        coverage={},
        safety_contract={},
    )
    summary = enforce_final_identifier_filter(
        envelope,
        {"identifier_mode": "exact", "normalized_identifier": "12020970001"},
    )
    # Direct-evidence corroboration is real backing even without a candidate page.
    assert [r["candidate_value"] for r in envelope.candidate_evidence] == ["120-20970-001"]
    assert summary["query_echo_drop_count"] == 0


def test_planner_seed_is_proposal_only_and_engram_aware():
    seed = build_planner_seed(
        "Find VS4956",
        {"identifier_mode": "exact", "requested_identifier": "VS4956"},
        "exact_identifier_lookup",
        engram_policy={"selected_atoms": ["exact_identifier_fidelity"]},
    )
    assert seed["planner_mode"] == "proposal_only"
    assert seed["engram_policy_available"] is True
    assert seed["execution_enabled"] is False
    assert seed["answer_permission"] is False


def test_grounded_allowlisted_planner_proposal_is_accepted():
    result = validate_planner_proposal(
        {
            "identifier_mode": "exact",
            "identifier": "VS4956",
            "suggested_routes": ["exact_identifier_lookup"],
            "suggested_tunnels": ["normal_source_truth"],
            "answer_permission": False,
        },
        query="Find VS4956",
        allowed_routes=["exact_identifier_lookup"],
        allowed_tunnels=["normal_source_truth"],
    )
    assert result["quality_status"] == "PASS"
    assert result["execution_enabled"] is False


def test_planner_proposal_rejects_invented_identifier():
    result = validate_planner_proposal(
        {"identifier": "INVENTED123"},
        query="Find VS4956",
        allowed_routes=[],
        allowed_tunnels=[],
    )
    assert result["quality_status"] == "FAIL"
    assert "identifier_not_grounded_in_query" in result["failures"]


def test_planner_proposal_rejects_unapproved_route():
    result = validate_planner_proposal(
        {"suggested_routes": ["source_truth_write"]},
        query="hello",
        allowed_routes=["safe_general_chat"],
        allowed_tunnels=[],
    )
    assert "route_not_allowlisted:source_truth_write" in result["failures"]


def test_planner_proposal_rejects_unapproved_tunnel():
    result = validate_planner_proposal(
        {"suggested_tunnels": ["postgres_write"]},
        query="Find VS4956",
        allowed_routes=[],
        allowed_tunnels=["normal_source_truth"],
    )
    assert "tunnel_not_allowlisted:postgres_write" in result["failures"]


def test_planner_proposal_rejects_unsafe_permission():
    result = validate_planner_proposal(
        {"answer_permission": True},
        query="Find VS4956",
        allowed_routes=[],
        allowed_tunnels=[],
    )
    assert "unsafe_true:answer_permission" in result["failures"]
    assert result["answer_permission"] is False


def test_general_source_benchmark_route_mapping_requires_semantic_route():
    routes = expected_h30_routes({
        "category": "general_source_truth",
        "expected_tunnel": "general_source_truth_retrieval",
    })
    assert routes == {"semantic_discovery"}


def test_exact_lookup_route_mapping_allows_navigation_for_where_query():
    routes = expected_h30_routes({"expected_tunnel": "exact_source_lookup"})
    assert "exact_identifier_lookup" in routes
    assert "document_page_navigation" in routes


def test_descriptive_ata_route_mapping_allows_ata_discovery():
    routes = expected_h30_routes({"expected_tunnel": "descriptive_part_discovery"})
    assert "ata_system_discovery" in routes


def test_health_exposes_planner_readiness_but_keeps_execution_off():
    health = phase4_3_1_health()
    assert health["validated_llm_planner_ready"] is True
    assert health["llm_planner_proposal_only"] is True
    assert health["llm_planner_execution_enabled"] is False
    for key in (
        "answer_permission", "final_answer_allowed", "can_answer_directly",
        "can_prove_claims", "source_truth_mutation_allowed", "postgres_write_attempt",
        "qdrant_write_attempt", "opensearch_write_attempt",
    ):
        assert health[key] is False


def _semantic_response(route: str):
    return {
        "choices": [{"message": {"content": (
            "## Answer\n\nNo direct proof.\n\n## Evidence\n\nNone.\n\n"
            "## Engineering confidence\n\nInsufficient.\n\n## Limits\n\n- More evidence required."
        )}}],
        "trace_net": {
            "route": route,
            "query_atoms": {"identifier_mode": "none"},
            "evidence_envelope": {
                "candidate_evidence": [],
                "direct_evidence": [],
                "source_resolution": [],
                "claim_evidence": {},
            },
            "citations": [],
            "citation_count": 0,
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        },
    }


def test_semantic_benchmark_rejects_manual_overview_clarification_route():
    from scripts.run_trace_net_h30_phase4_3_semantic_benchmark_v1 import evaluate_semantic_response

    result = evaluate_semantic_response(
        query="Describe the manual at a high level",
        status_code=200,
        response=_semantic_response("clarification_no_evidence"),
        record={
            "category": "general_source_truth",
            "expected_tunnel": "general_source_truth_retrieval",
        },
    )
    assert result["quality_status"] == "FAIL"
    assert any(item.startswith("route_not_suitable") for item in result["failures"])


def test_semantic_benchmark_accepts_manual_overview_semantic_route():
    from scripts.run_trace_net_h30_phase4_3_semantic_benchmark_v1 import evaluate_semantic_response

    result = evaluate_semantic_response(
        query="Describe the manual at a high level",
        status_code=200,
        response=_semantic_response("semantic_discovery"),
        record={
            "category": "general_source_truth",
            "expected_tunnel": "general_source_truth_retrieval",
        },
    )
    assert result["quality_status"] == "PASS"
