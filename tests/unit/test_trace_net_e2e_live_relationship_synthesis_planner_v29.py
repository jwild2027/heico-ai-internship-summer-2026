from pathlib import Path

from tiff.trace_net_e2e_live_relationship_synthesis_planner_v29 import (
    build_relationship_guidance,
    build_state,
    evaluate_quality,
    extract_seed_terms,
    find_seed_evidence,
    is_relationship_query,
    relationship_mode,
    run_live_query_v29,
)


def _write_json(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _adapter(tmp_path: Path) -> Path:
    p = tmp_path / "adapter.json"
    _write_json(
        p,
        '''{
          "documents": [
            {"record_id":"r1","page_id":"t_p_120_1176_p000003","field_name":"covered_part_number","normalized_value":"120-36833-503"},
            {"record_id":"r2","page_id":"t_p_120_1176_p000005","field_name":"manual_page_reference","normalized_value":"25-21-00"},
            {"record_id":"r3","page_id":"t_p_120_1176_p000027","field_name":"ipl_text","normalized_value":"ILLUSTRATED PARTS LIST"}
          ]
        }''',
    )
    return p


def _page_context(tmp_path: Path) -> Path:
    p = tmp_path / "page_context.json"
    _write_json(
        p,
        '''{
          "page_contexts": [
            {"page_id":"t_p_120_1176_p000003","summary":"Applicability/parts page."},
            {"page_id":"t_p_120_1176_p000004","summary":"Nearby related page."},
            {"page_id":"t_p_120_1176_p000005","summary":"Manual reference page."}
          ]
        }''',
    )
    return p


def _leiden(tmp_path: Path) -> Path:
    p = tmp_path / "leiden.json"
    _write_json(
        p,
        '''{
          "communities": [
            {"community_id":"tracenet_community_00001","page_ids":["t_p_120_1176_p000003","t_p_120_1176_p000004","t_p_120_1176_p000005"]}
          ]
        }''',
    )
    return p


def test_seed_extraction_and_relationship_classification():
    q = "Explain how part number 120-36833-503 relates to manual reference 25-21-00"
    seeds = extract_seed_terms(q)
    assert seeds["part_numbers"] == ["120-36833-503"]
    assert seeds["manual_references"] == ["25-21-00"]
    assert is_relationship_query(q)
    assert relationship_mode(q) == "relationship_synthesis"


def test_find_seed_evidence_exact_only(tmp_path: Path):
    state = build_state(_adapter(tmp_path), page_context_v2_path=_page_context(tmp_path), leiden_communities_path=_leiden(tmp_path))
    seeds = extract_seed_terms("What pages are related to part number 120-36833-503?")
    rows = find_seed_evidence(state["exact_search_documents"], seeds)
    assert len(rows) == 1
    assert rows[0]["page_id"] == "t_p_120_1176_p000003"
    assert rows[0]["citation_id"] == 1


def test_relationship_guidance_uses_leiden_without_proof(tmp_path: Path):
    state = build_state(_adapter(tmp_path), page_context_v2_path=_page_context(tmp_path), leiden_communities_path=_leiden(tmp_path))
    guidance = build_relationship_guidance(
        ["t_p_120_1176_p000003"],
        state["page_summaries"],
        state["page_to_community"],
        state["community_to_pages"],
    )
    assert guidance
    assert guidance[0]["proof_authority"] is False
    assert "t_p_120_1176_p000004" in guidance[0]["candidate_page_ids"]


def test_relationship_navigation_response_is_guidance_only(tmp_path: Path):
    state = build_state(_adapter(tmp_path), page_context_v2_path=_page_context(tmp_path), leiden_communities_path=_leiden(tmp_path))
    result = run_live_query_v29("What pages are related to part number 120-36833-503?", state, llm_mode="simulate")
    assert result["relationship_query"] is True
    assert result["response_mode"] == "relationship_navigation"
    assert result["relationship_proof_violation"] is False
    assert result["source_truth_seed_evidence_count"] == 1
    assert result["relationship_guidance_count"] >= 1
    assert "guidance only" in result["final_answer"].lower()


def test_relationship_synthesis_uses_simulated_draft_but_gated_answer(tmp_path: Path):
    state = build_state(_adapter(tmp_path), page_context_v2_path=_page_context(tmp_path), leiden_communities_path=_leiden(tmp_path))
    result = run_live_query_v29(
        "Explain how part number 120-36833-503 relates to manual reference 25-21-00",
        state,
        llm_mode="simulate",
    )
    assert result["response_mode"] == "relationship_synthesis"
    assert result["llm_status"] == "LLM_SIMULATED_RELATIONSHIP_DRAFT"
    assert result["relationship_proof_violation"] is False
    assert "does not by itself prove" in result["final_answer"]


def test_non_relationship_query_delegates_to_v28(tmp_path: Path):
    state = build_state(_adapter(tmp_path), page_context_v2_path=_page_context(tmp_path), leiden_communities_path=_leiden(tmp_path))
    result = run_live_query_v29("Find part number 120-36833-503", state, llm_mode="simulate")
    assert result["relationship_query"] is False
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_FINAL_GATE_PASS"


def test_build_quality_with_standard_samples(tmp_path: Path):
    state = build_state(
        _adapter(tmp_path),
        page_context_v2_path=_page_context(tmp_path),
        leiden_communities_path=_leiden(tmp_path),
        include_standard_demo_queries=True,
    )
    quality, checks = evaluate_quality(
        state,
        min_exact_search_documents=3,
        min_endpoint_routes=4,
        min_sample_queries=8,
        min_sample_successes=8,
        min_stage_timing_records=8,
        min_relationship_samples=4,
        min_relationship_guidance_samples=3,
        min_relationship_synthesis_samples=1,
        max_relationship_proof_violations=0,
        require_no_answer_permission=True,
    )
    assert quality == "PASS", checks


def test_missing_relationship_seed_is_audit_only(tmp_path: Path):
    state = build_state(_adapter(tmp_path), page_context_v2_path=_page_context(tmp_path), leiden_communities_path=_leiden(tmp_path))
    result = run_live_query_v29("What pages are related to part number 999-99999-999?", state, llm_mode="simulate")
    assert result["final_gate_status"] == "LIVE_RELATIONSHIP_AUDIT_ONLY"
    assert result["citation_like_count"] == 0
