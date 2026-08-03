from scripts.benchmark.serving.serve_trace_net_full_gemma_user_query_canary_v1 import (
    append_followups,
    validate_composed_answer,
)


def test_figure_with_comma_sheet_is_allowed():
    trace = {"citations": [{"citation_id": 1, "figure_refs": ["Figure 15, Sheet 1"]}]}
    assert validate_composed_answer(
        "The visual candidate is Figure 15, Sheet 1 [1].",
        upstream_answer="TRACE-Net found a visual candidate.",
        trace=trace,
    ) == []


def test_ocr_dash_igure_allows_normalized_figure():
    trace = {"citations": [{"citation_id": 1, "normalized_value": "-igure 80 Sheet 2"}]}
    assert validate_composed_answer(
        "The row appears in Figure 80 [1].",
        upstream_answer="TRACE-Net found matching table text.",
        trace=trace,
    ) == []


def test_unseen_figure_is_rejected():
    trace = {"citations": [{"citation_id": 1, "normalized_value": "Figure 80"}]}
    failures = validate_composed_answer(
        "The row appears in Figure 99 [1].",
        upstream_answer="TRACE-Net found matching table text.",
        trace=trace,
    )
    assert "unsupported_figure_reference:figure 99" in failures


def test_followups_visible_on_fallback():
    answer = append_followups(
        "TRACE-Net found source-backed evidence.",
        ["What exact row text should TRACE-Net match?", "Do you know the ATA chapter?"],
        should_append=True,
    )
    assert "Helpful follow-up questions:" in answer
    assert "What exact row text should TRACE-Net match?" in answer
