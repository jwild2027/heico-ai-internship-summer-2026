from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_reasoned_response_draft_v12 import (
    build_report,
    parse_source_truth_evidence_from_prompt,
    quality_checks,
    write_report_files,
)


def sample_prompt_contracts() -> dict:
    prompt = """TRACE-NET LLM PROMPT CONTRACT v11

USER QUESTION:
Find part number 120-36834-509

QUERY INTENT:
covered_part_number

SELF-RAG STATUS:
SELF_RAG_CONTEXT_READY

CRAG STATUS:
CRAG_NO_RETRY_NEEDED

SOURCE-TRUTH EVIDENCE (ONLY THIS BOX CAN SUPPORT FACTUAL CLAIMS):
- [1] page=t_p_120_1176_p000003 field=covered_part_number value=120-36834-509 source_tunnel=table_exact_search_tunnel tunnel_score=319
- [2] page=t_p_120_1176_p000003 field=covered_part_number value=120-36833-001 source_tunnel=table_exact_search_tunnel tunnel_score=199

GUIDANCE ONLY (not source truth, not proof):
- tunnel=page_summary_tunnel page=t_p_120_1176_p000003 authority=guidance_only_not_source_truth text=summary

ANSWER RULES:
- Cite every factual claim using SOURCE-TRUTH EVIDENCE.
"""
    return {
        "quality_status": "PASS",
        "prompt_contracts": [
            {
                "prompt_contract_id": "llm_prompt_contract_v11_0001",
                "prompt_contract_status": "LLM_PROMPT_CONTRACT_READY",
                "context_pack_id": "dynamic_context_pack_v8_0001",
                "user_query": "Find part number 120-36834-509",
                "query_intent": "covered_part_number",
                "prompt_text": prompt,
                "self_rag_ready": True,
                "crag_no_retry_needed": True,
                "source_self_rag_status": "SELF_RAG_CONTEXT_READY",
                "source_crag_plan_status": "CRAG_NO_RETRY_NEEDED",
                "graph_summary_proof_violation_count": 0,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        ],
    }


def test_parse_source_truth_evidence_from_prompt():
    prompt = sample_prompt_contracts()["prompt_contracts"][0]["prompt_text"]
    evidence = parse_source_truth_evidence_from_prompt(prompt)
    assert len(evidence) == 2
    assert evidence[0]["normalized_value"] == "120-36834-509"
    assert evidence[0]["page_id"] == "t_p_120_1176_p000003"


def test_build_report_reasoned_draft(tmp_path: Path):
    source_path = tmp_path / "prompt_contract.json"
    source_path.write_text(json.dumps(sample_prompt_contracts()), encoding="utf-8")
    report = build_report(source_path, {"min_prompt_contracts": 1, "min_reasoned_drafts": 1})
    assert report["quality_status"] == "PASS"
    assert report["summary"]["reasoned_draft_count"] == 1
    draft = report["reasoned_response_drafts"][0]
    assert draft["reasoned_response_draft_status"] == "REASONED_RESPONSE_DRAFT_READY_FOR_FINAL_GATE"
    assert "120-36834-509" in draft["draft_message"]["content"]
    assert draft["answer_permission"] is False
    assert draft["can_answer_directly"] is False


def test_quality_checks_pass(tmp_path: Path):
    source_path = tmp_path / "prompt_contract.json"
    source_path.write_text(json.dumps(sample_prompt_contracts()), encoding="utf-8")
    report = build_report(source_path)
    checks = quality_checks(
        report,
        {
            "min_prompt_contracts": 1,
            "min_reasoned_drafts": 1,
            "min_ready_reasoned_drafts": 1,
            "min_total_citations": 2,
            "min_drafts_with_limitations": 1,
            "min_drafts_ready_for_final_gate": 1,
            "max_graph_summary_proof_violations": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
        },
    )
    assert all(check["passed"] for check in checks)


def test_write_report_files(tmp_path: Path):
    source_path = tmp_path / "prompt_contract.json"
    source_path.write_text(json.dumps(sample_prompt_contracts()), encoding="utf-8")
    report = build_report(source_path)
    paths = write_report_files(report, tmp_path / "out")
    assert Path(paths["report_path"]).exists()
    assert Path(paths["drafts_jsonl_path"]).exists()
    assert Path(paths["citations_jsonl_path"]).exists()
    assert Path(paths["inspect_md_path"]).exists()


def test_audit_only_when_no_evidence(tmp_path: Path):
    data = sample_prompt_contracts()
    data["prompt_contracts"][0]["prompt_text"] = "TRACE-NET LLM PROMPT CONTRACT v11\nNO EVIDENCE"
    source_path = tmp_path / "prompt_contract.json"
    source_path.write_text(json.dumps(data), encoding="utf-8")
    report = build_report(source_path, {"min_ready_reasoned_drafts": 0, "min_total_citations": 0})
    draft = report["reasoned_response_drafts"][0]
    assert draft["reasoned_response_draft_status"] == "REASONED_RESPONSE_DRAFT_AUDIT_ONLY"
    assert "does not have citation-ready" in draft["draft_message"]["content"]


def test_table_text_draft_cites_every_page_mentioned(tmp_path: Path):
    prompt = """TRACE-NET LLM PROMPT CONTRACT v11

USER QUESTION:
Search table text MAINTENANCE MANUAL WITH

QUERY INTENT:
table_text

SELF-RAG STATUS:
SELF_RAG_CONTEXT_READY

CRAG STATUS:
CRAG_NO_RETRY_NEEDED

SOURCE-TRUTH EVIDENCE (ONLY THIS BOX CAN SUPPORT FACTUAL CLAIMS):
- [1] page=t_p_120_1176_p000027 field=ipl_text value=MAINTENANCE MANUAL WITH source_tunnel=table_exact_search_tunnel tunnel_score=319
- [2] page=t_p_120_1176_p000028 field=ipl_text value=MAINTENANCE MANUAL WITH source_tunnel=table_exact_search_tunnel tunnel_score=319
- [3] page=t_p_120_1176_p000029 field=ipl_text value=MAINTENANCE MANUAL WITH source_tunnel=table_exact_search_tunnel tunnel_score=319
- [4] page=t_p_120_1176_p000030 field=ipl_text value=MAINTENANCE MANUAL WITH source_tunnel=table_exact_search_tunnel tunnel_score=319
- [5] page=t_p_120_1176_p000031 field=ipl_text value=MAINTENANCE MANUAL WITH source_tunnel=table_exact_search_tunnel tunnel_score=319

GUIDANCE ONLY (not source truth, not proof):
- tunnel=page_summary_tunnel page=t_p_120_1176_p000027 authority=guidance_only_not_source_truth text=summary

ANSWER RULES:
- Cite every factual claim using SOURCE-TRUTH EVIDENCE.
"""
    data = {
        "quality_status": "PASS",
        "prompt_contracts": [
            {
                "prompt_contract_id": "llm_prompt_contract_v11_table_text",
                "prompt_contract_status": "LLM_PROMPT_CONTRACT_READY",
                "context_pack_id": "dynamic_context_pack_v8_table_text",
                "user_query": "Search table text MAINTENANCE MANUAL WITH",
                "query_intent": "table_text",
                "prompt_text": prompt,
                "self_rag_ready": True,
                "crag_no_retry_needed": True,
                "source_self_rag_status": "SELF_RAG_CONTEXT_READY",
                "source_crag_plan_status": "CRAG_NO_RETRY_NEEDED",
                "graph_summary_proof_violation_count": 0,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        ],
    }
    source_path = tmp_path / "prompt_contract_table_text.json"
    source_path.write_text(json.dumps(data), encoding="utf-8")
    report = build_report(source_path)
    content = report["reasoned_response_drafts"][0]["draft_message"]["content"]
    assert "t_p_120_1176_p000027 [1]" in content
    assert "t_p_120_1176_p000028 [2]" in content
    assert "t_p_120_1176_p000029 [3]" in content
    assert "t_p_120_1176_p000030 [4]" in content
    assert "t_p_120_1176_p000031 [5]" in content


def test_broad_covered_part_draft_cites_each_page_value_claim(tmp_path: Path):
    prompt = """TRACE-NET LLM PROMPT CONTRACT v11

USER QUESTION:
What maintenance manual pages mention covered part numbers?

QUERY INTENT:
covered_part_number

SELF-RAG STATUS:
SELF_RAG_CONTEXT_READY

CRAG STATUS:
CRAG_NO_RETRY_NEEDED

SOURCE-TRUTH EVIDENCE (ONLY THIS BOX CAN SUPPORT FACTUAL CLAIMS):
- [1] page=t_p_120_1176_p000003 field=covered_part_number value=120-36833-001 source_tunnel=table_exact_search_tunnel tunnel_score=199
- [2] page=t_p_120_1176_p000003 field=covered_part_number value=120-36833-003 source_tunnel=table_exact_search_tunnel tunnel_score=199
- [3] page=t_p_120_1176_p000003 field=covered_part_number value=120-36833-005 source_tunnel=table_exact_search_tunnel tunnel_score=199

GUIDANCE ONLY (not source truth, not proof):
- tunnel=page_summary_tunnel page=t_p_120_1176_p000003 authority=guidance_only_not_source_truth text=summary

ANSWER RULES:
- Cite every factual claim using SOURCE-TRUTH EVIDENCE.
"""
    data = {
        "quality_status": "PASS",
        "prompt_contracts": [
            {
                "prompt_contract_id": "llm_prompt_contract_v11_broad_covered_parts",
                "prompt_contract_status": "LLM_PROMPT_CONTRACT_READY",
                "context_pack_id": "dynamic_context_pack_v8_broad_covered_parts",
                "user_query": "What maintenance manual pages mention covered part numbers?",
                "query_intent": "covered_part_number",
                "prompt_text": prompt,
                "self_rag_ready": True,
                "crag_no_retry_needed": True,
                "source_self_rag_status": "SELF_RAG_CONTEXT_READY",
                "source_crag_plan_status": "CRAG_NO_RETRY_NEEDED",
                "graph_summary_proof_violation_count": 0,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        ],
    }
    source_path = tmp_path / "prompt_contract_broad_covered_parts.json"
    source_path.write_text(json.dumps(data), encoding="utf-8")
    report = build_report(source_path)
    content = report["reasoned_response_drafts"][0]["draft_message"]["content"]
    assert "page(s)" not in content
    assert "120-36833-001 on page t_p_120_1176_p000003 [1]" in content
    assert "120-36833-003 on page t_p_120_1176_p000003 [2]" in content
    assert "120-36833-005 on page t_p_120_1176_p000003 [3]" in content
