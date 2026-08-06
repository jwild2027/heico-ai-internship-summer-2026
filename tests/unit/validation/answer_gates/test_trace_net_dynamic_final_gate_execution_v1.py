from pathlib import Path

from tiff.trace_net_dynamic_final_gate_execution_v1 import (
    build_dynamic_final_gate_execution,
    evaluate_group_for_dynamic_claim,
    quality_report,
    write_json,
)


def _group(**overrides):
    base = {
        "hybrid_v2_group_id": "g1",
        "hybrid_v2_rank": 1,
        "page_id": "t_p_120_1176_p000003",
        "citation_ids": ["cite:verified_part:t_p_120_1176_p000003:abc"],
        "part_numbers": ["120-46137-001"],
        "rag_buckets": ["verified_part_evidence"],
        "authorities": ["part_page_relationship"],
        "answer_support_candidate_count": 1,
        "exact_hit_count": 2,
        "semantic_group_count": 0,
        "hybrid_v2_score": 0.8,
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }
    base.update(overrides)
    return base


def test_evaluate_group_approves_cited_answer_support():
    query = {"query_id": "q", "query": "120-46137-001"}
    claim, blocked = evaluate_group_for_dynamic_claim(query, _group())
    assert blocked is None
    assert claim is not None
    assert claim["page_id"] == "t_p_120_1176_p000003"
    assert claim["citation_ids"]
    assert claim["can_answer_directly"] is True
    assert claim["source_truth_mutation_allowed"] is False


def test_evaluate_group_blocks_retrieval_only_without_authority():
    query = {"query_id": "q", "query": "120-46137-001"}
    claim, blocked = evaluate_group_for_dynamic_claim(
        query,
        _group(citation_ids=["cite:x"], rag_buckets=["table_cell_normalized"], authorities=["table_cell_retrieval_helper_only"], answer_support_candidate_count=0),
    )
    assert claim is None
    assert blocked is not None
    assert "no_answer_support_authority" in blocked["blocked_reason_codes"]


def test_build_dynamic_final_gate_execution_approves_safe_claim(tmp_path: Path):
    hybrid = {
        "quality_status": "PASS",
        "query_results": [
            {"query_id": "part", "query": "120-46137-001", "ranked_group_count": 1, "ranked_groups": [_group()]}
        ],
    }
    hybrid_path = tmp_path / "hybrid.json"
    write_json(hybrid_path, hybrid)
    report = build_dynamic_final_gate_execution(
        hybrid_v2_report_path=hybrid_path,
        final_answer_report_path=None,
        output_dir=tmp_path / "out",
        min_queries=1,
        require_hybrid_v2_quality_pass=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["dynamic_final_gate_approved_count"] == 1
    assert report["summary"]["final_claim_count"] == 1
    assert report["summary"]["uncited_final_claim_count"] == 0


def test_build_dynamic_final_gate_execution_blocks_unsafe_group(tmp_path: Path):
    hybrid = {
        "quality_status": "PASS",
        "query_results": [
            {"query_id": "part", "query": "120-46137-001", "ranked_group_count": 1, "ranked_groups": [_group(citation_ids=[])]}
        ],
    }
    hybrid_path = tmp_path / "hybrid.json"
    write_json(hybrid_path, hybrid)
    report = build_dynamic_final_gate_execution(hybrid_v2_report_path=hybrid_path, final_answer_report_path=None, output_dir=tmp_path / "out")
    assert report["quality_status"] == "PASS"
    assert report["summary"]["retrieval_only_result_count"] == 1
    assert report["summary"]["final_claim_count"] == 0
    assert report["summary"]["missing_citation_blocked_claim_count"] == 1


def test_final_artifact_query_is_reused_when_exact_match(tmp_path: Path):
    hybrid_path = tmp_path / "hybrid.json"
    final_path = tmp_path / "final.json"
    md_path = tmp_path / "answer.md"
    write_json(hybrid_path, {"quality_status": "PASS", "query_results": []})
    write_json(final_path, {"quality_status": "PASS", "query": "Which pages discuss manual revision history?", "final_answer_allowed": True, "final_claim_count": 7})
    md_path.write_text("# x\n\n## Final gated answer\nAuthorized answer.", encoding="utf-8")
    report = build_dynamic_final_gate_execution(
        hybrid_v2_report_path=hybrid_path,
        final_answer_report_path=final_path,
        final_answer_markdown_path=md_path,
        query="Which pages discuss manual revision history?",
        output_dir=tmp_path / "out",
        require_final_answer_quality_pass=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["query_results"][0]["answer_status"] == "FINAL_GATE_ARTIFACT_ANSWER"
    assert report["query_results"][0]["final_answer_allowed"] is True


def test_quality_report_fails_on_uncited_final_claim():
    report = {
        "query_results": [
            {"answer_status": "DYNAMIC_FINAL_GATE_APPROVED", "final_answer_allowed": True, "final_claims": [{"citation_ids": []}], "uncited_final_claim_count": 1}
        ],
        "summary": {"dynamic_gate_query_count": 1, "uncited_final_claim_count": 1, "retrieval_only_final_claim_count": 0, "feedback_as_proof_count": 0, "community_as_proof_count": 0, "category_as_proof_count": 0, "local_path_leak_count": 0, "raw_bytes_repr_count": 0, "source_truth_mutation_allowed_count": 0, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "opensearch_write_attempt_count": 0},
    }
    q = quality_report(report)
    assert q["status"] == "FAIL"
