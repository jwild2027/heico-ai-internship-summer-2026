from tiff.trace_net_page_context_overlay_quality import run_quality


def test_quality_passes_for_expected_counts():
    summary = {
        "status": "OK",
        "postgres_page_context_records": 509,
        "pages_with_context_input": 509,
        "postgres_page_context_graph_nodes": 509,
        "postgres_has_context_edges": 509,
        "postgres_tagged_as_edges": 1706,
        "postgres_highlights_part_edges": 1070,
        "missing_page_resolutions": 0,
        "postgres_context_direct_answer_records": 0,
        "postgres_context_canonical_source_truth_records": 0,
        "source_truth_mutation_records": 0,
    }
    thresholds = {
        "min_context_records": 509,
        "min_pages_with_context": 509,
        "min_context_graph_nodes": 509,
        "min_has_context_edges": 509,
        "min_tagged_as_edges": 1,
        "min_highlights_part_edges": 1,
        "max_missing_page_resolutions": 0,
        "max_direct_answer_context_records": 0,
        "max_canonical_source_truth_context_records": 0,
        "max_source_truth_mutations": 0,
    }
    report = run_quality(summary, thresholds)
    assert report["status"] == "OK"


def test_quality_fails_on_direct_answer_context():
    summary = {
        "status": "OK",
        "postgres_page_context_records": 10,
        "pages_with_context_input": 10,
        "postgres_page_context_graph_nodes": 10,
        "postgres_has_context_edges": 10,
        "postgres_tagged_as_edges": 0,
        "postgres_highlights_part_edges": 0,
        "missing_page_resolutions": 0,
        "postgres_context_direct_answer_records": 1,
        "postgres_context_canonical_source_truth_records": 0,
        "source_truth_mutation_records": 0,
    }
    thresholds = {
        "min_context_records": 1,
        "min_pages_with_context": 1,
        "min_context_graph_nodes": 1,
        "min_has_context_edges": 1,
        "min_tagged_as_edges": 0,
        "min_highlights_part_edges": 0,
        "max_missing_page_resolutions": 0,
        "max_direct_answer_context_records": 0,
        "max_canonical_source_truth_context_records": 0,
        "max_source_truth_mutations": 0,
    }
    report = run_quality(summary, thresholds)
    assert report["status"] == "FAIL"
