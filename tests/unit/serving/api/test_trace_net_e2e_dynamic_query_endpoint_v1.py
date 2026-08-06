from pathlib import Path
import json

from tiff.trace_net_e2e_dynamic_query_endpoint_v1 import (
    build_dynamic_ask_response,
    build_manifest,
    classify_query_intent,
    dynamic_retrieve,
    make_openai_chat_completion,
    query_terms,
)


def sample_docs():
    exact = [
        {"page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36833-001", "retrieval_source": "table_exact_search", "routing_boost": 1.0},
        {"page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36834-509", "retrieval_source": "table_exact_search", "routing_boost": 1.0},
        {"page_id": "t_p_120_1176_p000005", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "retrieval_source": "table_exact_search", "routing_boost": 1.0},
        {"page_id": "t_p_120_1176_p000027", "field_name": "ipl_figure_item_or_quantity", "normalized_value": "130", "retrieval_source": "table_exact_search", "routing_boost": 1.0},
        {"page_id": "t_p_120_1176_p000027", "field_name": "ipl_text", "normalized_value": "MAINTENANCE MANUAL WITH", "retrieval_source": "table_exact_search", "routing_boost": 1.0},
    ]
    bridge = [
        {"page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36833-001", "retrieval_source": "table_hybrid_bridge", "routing_boost": 1.35},
    ]
    return exact, bridge


def test_classify_query_intents():
    assert classify_query_intent("Find part number 120-36833-001") == "covered_part_number"
    assert classify_query_intent("Where is manual reference 25-21-00 used?") == "manual_page_reference"
    assert classify_query_intent("Find IPL item 130") == "ipl_figure_item_or_quantity"
    assert classify_query_intent("Search table text MAINTENANCE MANUAL WITH") == "table_text"
    assert classify_query_intent("What maintenance manual pages mention covered part numbers?") == "covered_part_number"


def test_query_terms_extracts_domain_terms():
    terms = query_terms("Find part number 120-36833-001 in 25-21-00")
    assert "120-36833-001" in terms
    assert "25-21-00" in terms


def test_dynamic_retrieve_finds_new_part_not_in_canned_demo():
    exact, bridge = sample_docs()
    result = dynamic_retrieve("Find part number 120-36834-509", exact, bridge, top_k=3)
    assert result["retrieval_status"] == "DYNAMIC_RETRIEVAL_MATCHED"
    assert result["hits"][0]["normalized_value"] == "120-36834-509"


def test_dynamic_ask_response_has_citations_and_no_authority():
    exact, bridge = sample_docs()
    retrieval = dynamic_retrieve("Find IPL item 130", exact, bridge, top_k=3)
    response = build_dynamic_ask_response("Find IPL item 130", retrieval)
    assert response["api_response_status"] == "citation_backed_dynamic_response_draft"
    assert response["citations"][0]["normalized_value"] == "130"
    assert response["answer_permission"] is False
    assert response["can_answer_directly"] is False
    assert response["source_truth_mutation_allowed"] is False


def test_openai_completion_is_clean_and_contains_citation_values():
    ask = {
        "message": {"role": "assistant", "content": "covered_part_number=120-36833-001 ont_p_120_1176_p000003"},
        "citations": [{"page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36833-001"}],
        "retrieval_status": "DYNAMIC_RETRIEVAL_MATCHED",
        "query_intent": "covered_part_number",
        "hit_count": 1,
        "safety": {"answer_permission": False},
    }
    out = make_openai_chat_completion("Find part number 120-36833-001", ask)
    content = out["choices"][0]["message"]["content"]
    assert "ont_p_" not in content
    assert "on t_p_120_1176_p000003" in content
    assert "value=120-36833-001" in content


def test_build_manifest(tmp_path: Path):
    exact_rows, bridge_rows = sample_docs()
    exact_path = tmp_path / "exact.json"
    bridge_path = tmp_path / "bridge.json"
    exact_path.write_text(json.dumps({"quality_status": "PASS", "exact_search_documents": exact_rows}), encoding="utf-8")
    bridge_path.write_text(json.dumps({"quality_status": "PASS", "bridge_records": bridge_rows}), encoding="utf-8")
    manifest = build_manifest(
        exact_path,
        bridge_path,
        tmp_path / "out",
        min_exact_search_documents=5,
        min_bridge_records=1,
        min_field_count=3,
        quality=True,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["dynamic_search_document_count"] == 6


def test_reranker_v2_suppresses_generic_number_for_part_queries():
    exact, bridge = sample_docs()
    exact.extend([
        {"page_id": "t_p_120_1176_p000032", "field_name": "ipl_text", "normalized_value": "NUMBER", "retrieval_source": "table_exact_search", "routing_boost": 1.0},
        {"page_id": "t_p_120_1176_p000037", "field_name": "ipl_text", "normalized_value": "NUMBER", "retrieval_source": "table_exact_search", "routing_boost": 1.0},
    ])
    result = dynamic_retrieve("Find part number 120-36834-509", exact, bridge, top_k=5)
    assert result["hits"][0]["field_name"] == "covered_part_number"
    assert result["hits"][0]["normalized_value"] == "120-36834-509"
    assert all(hit["normalized_value"] != "NUMBER" for hit in result["hits"])


def test_reranker_v2_normalizes_table_text_spacing():
    exact, bridge = sample_docs()
    exact.append({"page_id": "t_p_120_1176_p000029", "field_name": "ipl_text", "normalized_value": "MAINTENANCEMANUAL WITH", "retrieval_source": "table_exact_search", "routing_boost": 1.0})
    result = dynamic_retrieve("Search table text MAINTENANCE MANUAL WITH", exact, bridge, top_k=5)
    values = [hit["normalized_value"] for hit in result["hits"]]
    assert "MAINTENANCE MANUAL WITH" in values
    response = build_dynamic_ask_response("Search table text MAINTENANCE MANUAL WITH", result)
    citation_values = [c["normalized_value"] for c in response["citations"]]
    assert all("MAINTENANCEMANUAL" not in value for value in citation_values)


def test_dynamic_endpoint_v4_loads_tunnel_debug_metadata(tmp_path: Path):
    from tiff.trace_net_e2e_dynamic_query_endpoint_v1 import load_tunnel_debug_metadata

    report = {
        "quality_status": "PASS",
        "e2e_dynamic_query_tunnels_status": "E2E_DYNAMIC_QUERY_TUNNELS_READY_FOR_ENDPOINT_INTEGRATION",
        "dynamic_query_tunnel_contract": {
            "tunnels_are_routing_and_ranking_only": True,
            "graph_is_not_proof_authority": True,
            "summaries_are_not_source_truth": True,
            "answer_permission": False,
        },
        "summary": {
            "query_tunnel_plan_count": 5,
            "ready_query_tunnel_plan_count": 5,
            "total_tunnel_count": 20,
            "unique_tunnel_type_count": 4,
            "plans_with_graph_or_summary_tunnel_count": 0,
        },
        "artifact_states": [
            {"tunnel_type": "table_exact_search_tunnel", "present": True},
            {"tunnel_type": "table_hybrid_bridge_tunnel", "present": True},
            {"tunnel_type": "route_metadata_tunnel", "present": True},
            {"tunnel_type": "qdrant_page_profile_tunnel", "present": True},
            {"tunnel_type": "page_summary_tunnel", "present": False},
            {"tunnel_type": "graph_community_tunnel", "present": False},
        ],
    }
    p = tmp_path / "tunnels.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    debug = load_tunnel_debug_metadata(p)
    assert debug["tunnel_report_present"] is True
    assert "table_exact_search_tunnel" in debug["tunnels_available"]
    assert "qdrant_page_profile_tunnel" in debug["tunnels_available"]
    assert "page_summary_tunnel" in debug["missing_optional_tunnels"]
    assert debug["tunnel_authority_contract"]["graph_is_not_proof_authority"] is True
    assert debug["tunnel_authority_contract"]["answer_permission"] is False


def test_dynamic_endpoint_v4_attaches_tunnel_debug_to_ask_and_openai(tmp_path: Path):
    from tiff.trace_net_e2e_dynamic_query_endpoint_v1 import build_endpoint_state

    exact_rows, bridge_rows = sample_docs()
    exact_path = tmp_path / "trace_net_test_exact_v4.json"
    bridge_path = tmp_path / "trace_net_test_bridge_v4.json"
    tunnels_path = tmp_path / "trace_net_test_tunnels_v4.json"
    exact_path.write_text(json.dumps({"quality_status": "PASS", "exact_search_documents": exact_rows}), encoding="utf-8")
    bridge_path.write_text(json.dumps({"quality_status": "PASS", "bridge_records": bridge_rows}), encoding="utf-8")
    tunnels_path.write_text(json.dumps({
        "quality_status": "PASS",
        "e2e_dynamic_query_tunnels_status": "E2E_DYNAMIC_QUERY_TUNNELS_READY_FOR_ENDPOINT_INTEGRATION",
        "dynamic_query_tunnel_contract": {"tunnels_are_routing_and_ranking_only": True, "answer_permission": False},
        "summary": {"query_tunnel_plan_count": 5, "ready_query_tunnel_plan_count": 5, "total_tunnel_count": 20, "unique_tunnel_type_count": 4},
        "artifact_states": [
            {"tunnel_type": "table_exact_search_tunnel", "present": True},
            {"tunnel_type": "table_hybrid_bridge_tunnel", "present": True},
            {"tunnel_type": "route_metadata_tunnel", "present": True},
            {"tunnel_type": "qdrant_page_profile_tunnel", "present": True},
            {"tunnel_type": "page_summary_tunnel", "present": False},
        ],
    }), encoding="utf-8")
    state = build_endpoint_state(exact_path, bridge_path, dynamic_query_tunnels=tunnels_path)
    ask = state.ask("Find part number 120-36833-001")
    assert "tunnel_debug" in ask
    assert "table_exact_search_tunnel" in ask["tunnel_debug"]["tunnels_available"]
    out = make_openai_chat_completion("Find part number 120-36833-001", ask)
    assert "tunnels_available" in out["trace_net"]
    assert "table_hybrid_bridge_tunnel" in out["trace_net"]["tunnels_available"]
    assert "page_summary_tunnel" in out["trace_net"]["missing_optional_tunnels"]
    assert out["trace_net"]["tunnel_authority_contract"]["answer_permission"] is False


def test_dynamic_endpoint_v7_broad_covered_part_query_stays_on_part_route():
    exact, bridge = sample_docs()
    # The query includes the phrase "maintenance manual", which previously pushed
    # the endpoint into table_text and returned IPL text. It should stay on the
    # covered_part_number lane because the user asked about covered part numbers.
    result = dynamic_retrieve("What maintenance manual pages mention covered part numbers?", exact, bridge, top_k=3)
    assert result["query_intent"] == "covered_part_number"
    assert result["hits"]
    assert result["hits"][0]["field_name"] == "covered_part_number"
    assert all(hit["field_name"] == "covered_part_number" for hit in result["hits"])
    response = build_dynamic_ask_response("What maintenance manual pages mention covered part numbers?", result)
    assert response["citations"][0]["field_name"] == "covered_part_number"
    assert response["citations"][0]["page_id"] == "t_p_120_1176_p000003"
