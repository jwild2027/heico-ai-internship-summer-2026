from scripts.benchmark.serving.run_trace_net_fixed50_trace_server_gemma_multiquery_df_fallback_v1 import (
    query_variants,
    classify_bucket,
    grade,
    select_best_trace_response,
)


def test_df_eligibility_variants_include_bare_part_and_platform_claims():
    qs = query_variants("Is DF250040-501 eligible for A319 aircraft?", max_variants=20)
    assert "DF250040-501" in qs
    assert "DF250040501" in qs
    assert any("A319" in q and "eligibility" in q for q in qs)


def test_figure_variants_include_fig_spellings():
    qs = query_variants("What does figure 69 show?", max_variants=10)
    assert "Figure 69" in qs
    assert "FIG. 69" in qs


def test_bucket_df_first():
    assert classify_bucket("Can TRACE-Net prove DF250040-501 fits A319?") == "df250040-501"


def test_select_best_prefers_more_citations():
    tries = [
        {"try_index": 1, "query": "original", "status": "ok", "response": {"citations": []}},
        {"try_index": 2, "query": "DF250040-501", "status": "ok", "response": {"citations": [{"page_id": "p1"}, {"page_id": "p2"}]}}
    ]
    best = select_best_trace_response(tries, "Is DF250040-501 eligible for A319?")
    assert best["selected_query"] == "DF250040-501"
    assert best["citation_count"] == 2


def test_grade_catches_source_ready_without_citation():
    g = grade("- Source-trace status: source-trace-ready\n- Evidence used: Engram overlay", 0)
    assert g["source_trace_ready_without_citation"] is True


def test_grade_allows_policy_boundary_ready_without_citation():
    g = grade("- Source-trace status: policy-boundary-ready\n- Evidence used: Engram overlay", 0)
    assert g["source_trace_ready_without_citation"] is False
