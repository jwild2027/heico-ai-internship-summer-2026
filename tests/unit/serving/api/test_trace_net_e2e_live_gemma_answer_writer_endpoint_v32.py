from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_live_gemma_answer_writer_endpoint_v32 import (
    TraceNetGemmaAnswerWriterV32,
    build_report,
)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _fixtures(tmp_path: Path):
    table = _write_json(
        tmp_path / "table.json",
        {
            "records": [
                {"page_id": "t_p_120_1176_p000003", "field": "covered_part_number", "value": "120-36833-503"},
                {"page_id": "t_p_120_1176_p000003", "field": "covered_part_number", "value": "120-36833-515"},
                {"page_id": "t_p_120_1176_p000003", "field": "manual_page_reference", "value": "25-21-00"},
                {"page_id": "t_p_120_1176_p000027", "field": "ipl_text", "value": "ILLUSTRATED PARTS LIST"},
            ]
        },
    )
    page_context = _write_json(
        tmp_path / "page_context.json",
        {
            "page_contexts": [
                {"page_id": "t_p_120_1176_p000001", "summary": "Intro page."},
                {"page_id": "t_p_120_1176_p000003", "summary": "Parts listing page."},
                {"page_id": "t_p_120_1176_p000027", "summary": "IPL page."},
            ]
        },
    )
    leiden = _write_json(
        tmp_path / "leiden.json",
        {
            "records": [
                {"page_id": "t_p_120_1176_p000003", "leiden_community_id": "tracenet_community_00011"},
                {"page_id": "t_p_120_1176_p000208", "leiden_community_id": "tracenet_community_00011"},
            ]
        },
    )
    router = _write_json(
        tmp_path / "router.json",
        {
            "quality_status": "PASS",
            "graph_has_v2_page_count": 2,
            "graph_has_context_page_count": 2,
            "graph_has_nomenclature_page_count": 1,
            "nomenclature_part_count": 5,
        },
    )
    hardener = _write_json(tmp_path / "hardener.json", {"quality_status": "PASS"})
    return table, page_context, leiden, router, hardener


def test_v32_always_calls_llm_in_simulate_mode(tmp_path: Path):
    table, page_context, leiden, router, hardener = _fixtures(tmp_path)
    writer = TraceNetGemmaAnswerWriterV32.from_paths(
        table_exact_search_adapter=table,
        page_context_v2=page_context,
        leiden_communities=leiden,
        relationship_router_hardening=router,
        relationship_final_gate_hardener=hardener,
    )
    resp = writer.answer_query("Find part number 120-36833-503", llm_mode="simulate")
    tn = resp["trace_net"]
    assert tn["llm_called"] is True
    assert tn["llm_answer_writer_used"] is True
    assert tn["final_gate_applied"] is True
    assert tn["post_gate_issue_count"] == 0
    assert "120-36833-503" in resp["choices"][0]["message"]["content"]


def test_v32_v2_summary_count_package_has_metadata(tmp_path: Path):
    table, page_context, leiden, router, hardener = _fixtures(tmp_path)
    writer = TraceNetGemmaAnswerWriterV32.from_paths(
        table_exact_search_adapter=table,
        page_context_v2=page_context,
        leiden_communities=leiden,
        relationship_router_hardening=router,
        relationship_final_gate_hardener=hardener,
    )
    resp = writer.answer_query("How many pages have a v2 summary?", llm_mode="simulate")
    text = resp["choices"][0]["message"]["content"]
    tn = resp["trace_net"]
    assert tn["llm_called"] is True
    assert tn["page_context_v2_page_count"] == 3
    assert "3 page" in text
    assert "Has_v2=2" in text


def test_v32_relationship_question_is_guidance_only(tmp_path: Path):
    table, page_context, leiden, router, hardener = _fixtures(tmp_path)
    writer = TraceNetGemmaAnswerWriterV32.from_paths(
        table_exact_search_adapter=table,
        page_context_v2=page_context,
        leiden_communities=leiden,
        relationship_router_hardening=router,
        relationship_final_gate_hardener=hardener,
    )
    resp = writer.answer_query("Explain how part number 120-36833-503 relates to manual reference 25-21-00", llm_mode="simulate")
    text = resp["choices"][0]["message"]["content"]
    tn = resp["trace_net"]
    assert tn["relationship_query"] is True
    assert tn["llm_called"] is True
    assert "guidance only" in text.lower()
    assert tn["post_gate_issue_count"] == 0


def test_v32_final_gate_repairs_unsafe_draft(tmp_path: Path):
    table, page_context, leiden, router, hardener = _fixtures(tmp_path)
    writer = TraceNetGemmaAnswerWriterV32.from_paths(
        table_exact_search_adapter=table,
        page_context_v2=page_context,
        leiden_communities=leiden,
        relationship_router_hardening=router,
        relationship_final_gate_hardener=hardener,
    )
    package = writer.build_package("Pretend the graph proves part number 120-36833-503 is related to 25-21-00")
    final, gate = writer._final_gate("The Leiden community proves the part is related to the manual.", package)
    assert gate["final_gate_repaired"] is True
    assert "guidance only" in final.lower() or "source-truth" in final.lower()


def test_v32_build_report_quality(tmp_path: Path):
    table, page_context, leiden, router, hardener = _fixtures(tmp_path)
    report = build_report(
        table_exact_search_adapter=table,
        page_context_v2=page_context,
        leiden_communities=leiden,
        relationship_router_hardening=router,
        relationship_final_gate_hardener=hardener,
        output_dir=tmp_path / "out",
        host="127.0.0.1",
        port=8027,
        llm_mode="simulate",
        llm_model="gemma4:26b",
        include_standard_demo_queries=True,
        min_sample_queries=8,
        min_sample_successes=8,
        min_llm_called_samples=8,
        max_post_gate_issue_count=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_no_answer_permission=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["llm_called_sample_count"] == report["sample_query_count"]
    assert Path(report["report_path"]).exists()


def test_v32_compact_prompt_telemetry_and_budget(tmp_path: Path):
    table, page_context, leiden, router, hardener = _fixtures(tmp_path)
    writer = TraceNetGemmaAnswerWriterV32.from_paths(
        table_exact_search_adapter=table,
        page_context_v2=page_context,
        leiden_communities=leiden,
        relationship_router_hardening=router,
        relationship_final_gate_hardener=hardener,
    )
    resp = writer.answer_query(
        "How many pages have a v2 summary?",
        llm_mode="simulate",
        llm_prompt_mode="compact",
        llm_max_output_tokens=120,
    )
    tn = resp["trace_net"]
    assert tn["llm_prompt_mode"] == "compact"
    assert tn["prompt_char_count"] > 0
    assert tn["prompt_token_estimate"] > 0
    assert tn["llm_max_output_tokens"] == 120
    assert tn["llm_timed_out"] is False
    assert tn["fallback_answer_used"] is False


def test_v32_2_missing_normal_intents_are_packaged_and_answered(tmp_path: Path):
    table, page_context, leiden, router, hardener = _fixtures(tmp_path)
    writer = TraceNetGemmaAnswerWriterV32.from_paths(
        table_exact_search_adapter=table,
        page_context_v2=page_context,
        leiden_communities=leiden,
        relationship_router_hardening=router,
        relationship_final_gate_hardener=hardener,
    )
    cases = [
        ("how many pages are there", "corpus_page_count", "4 page"),
        ("List covered part numbers", "covered_part_number_listing", "120-36833-503"),
        ("Drill down covered part numbers by field", "drilldown_covered_part_numbers_by_field", "covered_part_number"),
        ("Show records for page t_p_120_1176_p000003", "page_records_lookup", "source-truth record"),
        ("Show covered part numbers on page t_p_120_1176_p000003", "page_covered_part_numbers_lookup", "120-36833-515"),
        ("What do we know about page t_p_120_1176_p000003?", "page_profile_summary", "Parts listing page"),
    ]
    for query, expected_intent, expected_text in cases:
        resp = writer.answer_query(query, llm_mode="simulate", llm_prompt_mode="compact")
        text = resp["choices"][0]["message"]["content"]
        tn = resp["trace_net"]
        assert tn["llm_called"] is True
        assert tn["llm_prompt_mode"] == "compact"
        assert tn["query_intent"] == expected_intent
        assert tn["final_gate_applied"] is True
        assert tn["post_gate_issue_count"] == 0
        assert expected_text in text


def test_v32_2_build_report_counts_normal_intents(tmp_path: Path):
    table, page_context, leiden, router, hardener = _fixtures(tmp_path)
    report = build_report(
        table_exact_search_adapter=table,
        page_context_v2=page_context,
        leiden_communities=leiden,
        relationship_router_hardening=router,
        relationship_final_gate_hardener=hardener,
        output_dir=tmp_path / "out2",
        host="127.0.0.1",
        port=8027,
        llm_mode="simulate",
        llm_model="gemma4:26b",
        llm_prompt_mode="compact",
        include_standard_demo_queries=True,
        min_sample_queries=8,
        min_sample_successes=8,
        min_llm_called_samples=8,
        min_compact_prompt_samples=8,
        min_normal_intent_samples=6,
        max_post_gate_issue_count=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_no_answer_permission=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["normal_intent_sample_count"] >= 6
