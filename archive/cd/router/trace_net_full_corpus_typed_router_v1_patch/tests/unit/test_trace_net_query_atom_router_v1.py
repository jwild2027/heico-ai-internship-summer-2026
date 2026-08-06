from tiff.trace_net_query_atom_router_v1 import analyze_query

def test_exact_part_routes_to_exact_source_lookup():
    result = analyze_query("Find part number 120-41824-003")
    assert result["selected_tunnel"] == "exact_source_lookup"
    assert result["execution_route"] == "normal_ask"
    assert result["atoms"]["part_numbers"] == ["120-41824-003"]

def test_partial_part_routes_to_guided_discovery():
    result = analyze_query("I only know the part starts with 24")
    assert result["selected_tunnel"] == "guided_candidate_discovery"
    assert result["execution_route"] == "guided_discovery"
    assert result["atoms"]["prefix"] == "24"

def test_visual_routes_to_visual():
    result = analyze_query("Show me figure 69 for the seat assembly")
    assert result["selected_tunnel"] == "visual_figure_retrieval"
    assert result["execution_route"] == "gemma_confirmed_image_visual"

def test_table_routes_to_table_tunnel():
    result = analyze_query("Search the illustrated parts list table for locking ring")
    assert result["selected_tunnel"] == "table_exact_or_structured_retrieval"
    assert result["execution_route"] == "normal_ask"

def test_procedure_routes_to_procedure_tunnel():
    result = analyze_query("What is the removal procedure for the armrest?")
    assert result["selected_tunnel"] == "procedure_warning_text_retrieval"

def test_safety_claim_has_priority():
    result = analyze_query("Is 120-41824-003 an approved interchangeable replacement and safe to install?")
    assert result["selected_tunnel"] == "safety_authority_search"
    assert result["execution_route"] == "normal_ask"
    assert result["final_answer_allowed"] is False
