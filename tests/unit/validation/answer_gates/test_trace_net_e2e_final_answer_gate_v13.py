from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_final_answer_gate_v13 import (
    build_final_answer_gate_report,
    critique_draft,
    quality_check,
)


def sample_citation(i=1, value="120-36834-509"):
    return {
        "answer_authority": "source_truth_evidence_only",
        "citation_id": f"citation_{i}",
        "citation_marker": f"[{i}]",
        "citation_ready": True,
        "evidence_id": f"evidence_{i:03d}",
        "field_name": "covered_part_number",
        "normalized_value": value,
        "page_id": "t_p_120_1176_p000003",
        "source_trace_ready": True,
        "source_tunnel": "table_exact_search_tunnel",
    }


def sample_draft(content=None):
    if content is None:
        content = (
            "TRACE-Net found part number 120-36834-509 as a covered part number "
            "on page t_p_120_1176_p000003 [1]. The evidence is sufficient to "
            "confirm the listing, but not enough to describe what the part physically is."
        )
    return {
        "reasoned_response_draft_id": "reasoned_response_draft_v12_0001",
        "reasoned_response_draft_status": "REASONED_RESPONSE_DRAFT_READY_FOR_FINAL_GATE",
        "prompt_contract_id": "llm_prompt_contract_v11_0001",
        "context_pack_id": "dynamic_context_pack_v8_0001",
        "user_query": "Find part number 120-36834-509",
        "query_intent": "covered_part_number",
        "draft_message": {"role": "assistant", "content": content},
        "citations": [sample_citation(1, "120-36834-509"), sample_citation(2, "120-36833-001")],
        "limitations": ["The evidence confirms listing only."],
        "page_ids": ["t_p_120_1176_p000003"],
        "field_counts": {"covered_part_number": 2},
        "graph_summary_proof_violation_count": 0,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def test_critique_draft_passes_supported_cited_draft():
    gate = critique_draft(sample_draft(), 1)
    assert gate["final_answer_gate_status"] == "FINAL_ANSWER_GATE_PASSED"
    assert gate["ready_for_webui_endpoint"] is True
    assert gate["citation_count"] == 2
    assert gate["unsupported_claim_count"] == 0
    assert gate["answer_permission"] is False


def test_critique_blocks_uncited_evidence_mention():
    draft = sample_draft("TRACE-Net found 120-36834-509 on page t_p_120_1176_p000003.")
    gate = critique_draft(draft, 1)
    assert gate["final_answer_gate_status"] == "FINAL_ANSWER_GATE_BLOCKED"
    assert any("unsupported_evidence_mentions" in b for b in gate["blockers"])


def test_critique_blocks_unknown_citation_marker():
    draft = sample_draft("TRACE-Net found part number 120-36834-509 [9].")
    gate = critique_draft(draft, 1)
    assert gate["final_answer_gate_status"] == "FINAL_ANSWER_GATE_BLOCKED"
    assert any("unknown_citation" in b for b in gate["blockers"])


def test_critique_blocks_invented_description():
    draft = sample_draft("Part number 120-36834-509 is a valve [1].")
    gate = critique_draft(draft, 1)
    assert gate["final_answer_gate_status"] == "FINAL_ANSWER_GATE_BLOCKED"
    assert "possible_invented_physical_part_description" in gate["blockers"]


def test_build_final_answer_gate_report_and_quality(tmp_path):
    source = {"reasoned_response_drafts": [sample_draft(), sample_draft()]}
    source_path = tmp_path / "v12.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    report = build_final_answer_gate_report(
        reasoned_response_draft_path=source_path,
        output_dir=tmp_path / "out",
        quality_args={
            "min_reasoned_drafts": 2,
            "min_final_gates": 2,
            "min_passed_final_gates": 2,
            "min_citation_supported_answers": 2,
            "min_total_citations": 4,
            "min_final_answers_ready_for_webui": 2,
            "min_answers_with_limitations": 2,
            "max_unsupported_claim_count": 0,
            "max_graph_summary_proof_violations": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_no_answer_permission": True,
        },
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["passed_final_gate_count"] == 2
    assert Path(report["report_path"]).exists()
    assert Path(report["records_jsonl_path"]).exists()
    assert Path(report["citations_jsonl_path"]).exists()
    assert Path(report["inspect_md_path"]).exists()


def test_quality_check_fails_thresholds():
    report = {"quality_status": "PASS", "summary": {"reasoned_draft_count": 0}}
    status, checks = quality_check(report, min_reasoned_drafts=1)
    assert status == "FAIL"
    assert any(not c["passed"] for c in checks)
