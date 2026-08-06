from tiff.trace_net_page_context_v2_quality import build_quality


def test_quality_passes_safe_summary():
    summary = {
        "status": "OK",
        "context_v2_records_generated": 509,
        "records_with_retrieval_cues": 509,
        "records_with_answerable_questions": 495,
        "direct_answer_context_records": 0,
        "canonical_source_truth_context_records": 0,
        "source_truth_mutation_records": 0,
        "postgres_context_v2_graph_nodes": 509,
        "postgres_has_context_v2_edges": 509,
    }
    thresholds = {
        "min_context_v2_records": 509,
        "min_pages_with_context_v2": 509,
        "min_records_with_retrieval_cues": 495,
        "min_records_with_answerable_questions": 495,
        "min_context_v2_graph_nodes": 509,
        "min_has_context_v2_edges": 509,
        "max_direct_answer_context_records": 0,
        "max_canonical_source_truth_context_records": 0,
        "max_source_truth_mutations": 0,
    }
    report = build_quality(summary, thresholds)
    assert report["status"] == "OK"


def test_quality_fails_direct_answer_context():
    summary = {
        "status": "OK",
        "context_v2_records_generated": 1,
        "records_with_retrieval_cues": 1,
        "records_with_answerable_questions": 1,
        "direct_answer_context_records": 1,
        "canonical_source_truth_context_records": 0,
        "source_truth_mutation_records": 0,
        "postgres_context_v2_graph_nodes": 1,
        "postgres_has_context_v2_edges": 1,
    }
    thresholds = {
        "min_context_v2_records": 1,
        "min_pages_with_context_v2": 1,
        "min_records_with_retrieval_cues": 1,
        "min_records_with_answerable_questions": 1,
        "min_context_v2_graph_nodes": 1,
        "min_has_context_v2_edges": 1,
        "max_direct_answer_context_records": 0,
        "max_canonical_source_truth_context_records": 0,
        "max_source_truth_mutations": 0,
    }
    report = build_quality(summary, thresholds)
    assert report["status"] == "FAIL"
    assert any(c["name"] == "direct_answer_context_records" and not c["ok"] for c in report["checks"])
