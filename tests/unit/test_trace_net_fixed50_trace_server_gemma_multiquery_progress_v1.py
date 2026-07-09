from scripts.run_trace_net_fixed50_trace_server_gemma_multiquery_progress_v1 import (
    build_query_variants,
    classify_bucket,
    citation_count,
    grade_answer,
    select_best_trace_response,
)


def test_build_query_variants_for_figure_69():
    variants = build_query_variants("What does figure 69 show?")
    assert variants[0] == "What does figure 69 show?"
    assert any("FIG. 69" in v for v in variants)
    assert len(variants) <= 6


def test_build_query_variants_for_df_part():
    variants = build_query_variants("Is DF250040-501 eligible for A319 aircraft?")
    assert any(v == "DF250040-501" for v in variants)
    assert any("paper towel dispenser" in v.lower() for v in variants)


def test_citation_count_schema_flexible():
    data = {"citations": [{"page_id": "p1", "citation_id": "c1"}], "nested": {"proof_context": [{"source_trace_ready": True}]}}
    assert citation_count(data) == 2


def test_select_best_trace_response_prefers_more_citations():
    rows = [
        {"query_variant": "a", "citation_count": 0, "trace_response": {}},
        {"query_variant": "b", "citation_count": 3, "trace_response": {"citations": [1, 2, 3]}},
    ]
    assert select_best_trace_response(rows)["query_variant"] == "b"


def test_grade_policy_ready_is_not_source_trace_without_citation():
    grade = grade_answer("Source-trace status: policy-boundary-ready. Engram is guidance only.", 0)
    assert grade["source_trace_ready_without_citation"] is False
    assert grade["engram_policy_used_as_source_proof"] is False


def test_classify_bucket():
    assert classify_bucket("What does figure 69 show?") == "figure_69"
    assert classify_bucket("Find DF250040-501") == "df250040-501"
