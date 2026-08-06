from tiff.trace_net_query_atom_router_v1 import analyze_query


def test_descriptive_hinge_routes_to_guided_and_asks_part_number_company():
    result = analyze_query("I would like a part that is a hinge")
    assert result["execution_route"] == "guided_discovery"
    assert result["selected_tunnel"] == "descriptive_part_discovery"
    assert result["clarification_required"] is True
    assert "part_number" in result["follow_up_topics"]
    assert "manufacturer" in result["follow_up_topics"]
    text = " ".join(result["clarifying_questions"]).lower()
    assert "part-number" in text or "part number" in text
    assert "manufacturer" in text or "company" in text


def test_partial_prefix_keeps_candidate_discovery():
    result = analyze_query("I only know the part starts with 123")
    assert result["execution_route"] == "guided_discovery"
    assert result["selected_tunnel"] == "guided_candidate_discovery"
    assert len(result["clarifying_questions"]) >= 4


def test_exact_part_does_not_force_clarification():
    result = analyze_query("Find part number 120-41824-003")
    assert result["execution_route"] == "normal_ask"
    assert result["selected_tunnel"] == "exact_source_lookup"
    assert result["clarification_required"] is False
    assert result["clarifying_questions"] == []


def test_broad_procedure_has_contextual_followups():
    result = analyze_query("What is the removal procedure for the armrest?")
    assert result["selected_tunnel"] == "procedure_warning_text_retrieval"
    assert result["clarification_recommended"] is True
    assert "component_identity" in result["follow_up_topics"]
    assert "manual_revision" in result["follow_up_topics"]


def test_safety_questions_ask_for_authority_not_guessing():
    result = analyze_query("Is this hinge an approved interchangeable replacement?")
    assert result["selected_tunnel"] == "safety_authority_search"
    assert "source_authority" in result["follow_up_topics"]
    assert result["final_answer_allowed"] is False
