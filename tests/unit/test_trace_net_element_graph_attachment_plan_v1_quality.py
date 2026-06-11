from tiff.trace_net_element_graph_attachment_plan_v1 import evaluate_quality


def base_summary():
    return {
        "page_count": 509,
        "page_node_count": 509,
        "node_plan_count": 7000,
        "edge_plan_count": 9000,
        "table_node_plan_count": 495,
        "table_row_node_plan_count": 1414,
        "table_cell_node_plan_count": 3090,
        "visual_node_plan_count": 1018,
        "fishnet_node_plan_count": 509,
        "citation_edge_plan_count": 1426,
        "confirmed_blank_pages_preserve_source_trace_count": 14,
        "orphan_edge_count": 0,
        "missing_page_id_count": 0,
        "answer_capable_without_citation_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "direct_answer_allowed_count": 0,
        "claim_proof_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "unsafe_attachment_record_count": 0,
        "forbidden_property_leak_count": 0,
        "source_summaries": {
            "page_registry_quality_status": "PASS",
            "fishnet_refinement_quality_status": "PASS",
        },
    }


def test_quality_passes_strict_summary():
    quality = evaluate_quality(
        base_summary(),
        {
            "require_page_count": 509,
            "min_page_nodes": 509,
            "min_element_node_plans": 1000,
            "min_edge_plans": 1000,
            "min_table_node_plans": 20,
            "min_visual_node_plans": 100,
            "min_fishnet_node_plans": 509,
            "min_citation_edge_plans": 1,
            "min_confirmed_blank_preserve_source_trace": 14,
            "require_page_registry_quality_pass": True,
            "require_fishnet_refinement_quality_pass": True,
        },
    )
    assert quality["status"] == "PASS"


def test_quality_fails_on_orphan_edges():
    summary = base_summary()
    summary["orphan_edge_count"] = 2
    quality = evaluate_quality(summary, {"require_page_count": 509})
    assert quality["status"] == "FAIL"
    assert any(c["name"] == "no_orphan_edges" and not c["passed"] for c in quality["checks"])


def test_quality_fails_on_source_truth_mutation():
    summary = base_summary()
    summary["source_truth_mutation_allowed_count"] = 1
    quality = evaluate_quality(summary, {})
    assert quality["status"] == "FAIL"
    assert any(c["name"] == "no_source_truth_mutation_allowed" and not c["passed"] for c in quality["checks"])


def test_quality_fails_when_source_quality_required():
    summary = base_summary()
    summary["source_summaries"]["fishnet_refinement_quality_status"] = "FAIL"
    quality = evaluate_quality(summary, {"require_fishnet_refinement_quality_pass": True})
    assert quality["status"] == "FAIL"
