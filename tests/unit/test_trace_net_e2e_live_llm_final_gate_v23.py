from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_live_llm_final_gate_v23 import build_report, render_markdown, write_report_files


def prompt_report():
    table_context = """TRACE-NET CONTEXT PACK

SOURCE-TRUTH EVIDENCE (direct proof authority; cite these for factual claims):
- [1] page=t_p_120_1176_p000027 field=ipl_text value=MAINTENANCE MANUAL WITH

NEARBY SOURCE-TRUTH CONTEXT (source-truth records, but not direct query matches; use cautiously):
- [2] page=t_p_120_1176_p000027 field=ipl_text value=ILLUSTRATED PARTS LIST
- [3] page=t_p_120_1176_p000027 field=ipl_text value=STOCK
- [4] page=t_p_120_1176_p000027 field=ipl_text value=i occurrence_count=2

EVIDENCE DEDUPLICATION / HYGIENE:
{}

GRAPH / LEIDEN GUIDANCE (navigation only; not proof):
[]

V2 SUMMARY GUIDANCE (meaning/compression only; not proof):
[]

AGGREGATION / CAPPING METADATA:
{
  "total_match_count": 188,
  "returned_match_count": 10,
  "result_was_capped": true,
  "more_results_available": true,
  "high_degree_node_detected": true,
  "available_drilldowns": ["document", "page", "field_type"]
}

SELF-RAG / CRAG STATUS:
{"self_rag_status":"CONTEXT_READY_FOR_LLM","crag_status":"NO_RETRY_NEEDED"}

ANSWER RULES:
{"cite_every_factual_claim": true}
"""
    manual_context = """TRACE-NET CONTEXT PACK

SOURCE-TRUTH EVIDENCE (direct proof authority; cite these for factual claims):
- [1] page=t_p_120_1176_p000005 field=manual_page_reference value=25-21-00 occurrence_count=10

NEARBY SOURCE-TRUTH CONTEXT (source-truth records, but not direct query matches; use cautiously):
- None

GRAPH / LEIDEN GUIDANCE (navigation only; not proof):
[]

V2 SUMMARY GUIDANCE (meaning/compression only; not proof):
[{"summary":"This page appears to be a parts list and index."}]

AGGREGATION / CAPPING METADATA:
{
  "total_match_count": 50,
  "returned_match_count": 10,
  "result_was_capped": true,
  "more_results_available": true,
  "high_degree_node_detected": true,
  "available_drilldowns": ["document", "page"]
}

SELF-RAG / CRAG STATUS:
{"self_rag_status":"CONTEXT_READY_FOR_LLM","crag_status":"NO_RETRY_NEEDED"}

ANSWER RULES:
{"cite_every_factual_claim": true}
"""
    part_context = """TRACE-NET CONTEXT PACK

SOURCE-TRUTH EVIDENCE (direct proof authority; cite these for factual claims):
- [1] page=t_p_120_1176_p000003 field=covered_part_number value=120-36834-509

NEARBY SOURCE-TRUTH CONTEXT (source-truth records, but not direct query matches; use cautiously):
- None

GRAPH / LEIDEN GUIDANCE (navigation only; not proof):
[]

V2 SUMMARY GUIDANCE (meaning/compression only; not proof):
[]

AGGREGATION / CAPPING METADATA:
{"total_match_count":1,"returned_match_count":1,"result_was_capped":false,"more_results_available":false,"high_degree_node_detected":false}

SELF-RAG / CRAG STATUS:
{"self_rag_status":"CONTEXT_READY_FOR_LLM","crag_status":"NO_RETRY_NEEDED"}

ANSWER RULES:
{"cite_every_factual_claim": true}
"""
    return {
        "prompt_contracts": [
            {"prompt_contract_id": "contract_part", "context_pack_id": "pack_part", "user_query": "Find part number 120-36834-509", "messages": [{"role": "user", "content": part_context}]},
            {"prompt_contract_id": "contract_manual", "context_pack_id": "pack_manual", "user_query": "Where is manual reference 25-21-00 used?", "messages": [{"role": "user", "content": manual_context}]},
            {"prompt_contract_id": "contract_table", "context_pack_id": "pack_table", "user_query": "Search table text MAINTENANCE MANUAL WITH", "messages": [{"role": "user", "content": table_context}]},
        ]
    }


def draft_report():
    return {
        "llm_drafts": [
            {"llm_draft_id": "draft_part", "prompt_contract_id": "contract_part", "context_pack_id": "pack_part", "user_query": "Find part number 120-36834-509", "draft_text": "Part number 120-36834-509 is identified on page t_p_120_1176_p000003 [1]."},
            {"llm_draft_id": "draft_manual", "prompt_contract_id": "contract_manual", "context_pack_id": "pack_manual", "user_query": "Where is manual reference 25-21-00 used?", "draft_text": "Manual reference 25-21-00 is found on page t_p_120_1176_p000005 [1]. This page appears to be a parts list [V2 Summary Guidance]."},
            {"llm_draft_id": "draft_table", "prompt_contract_id": "contract_table", "context_pack_id": "pack_table", "user_query": "Search table text MAINTENANCE MANUAL WITH", "draft_text": "The text MAINTENANCE MANUAL WITH is found on page t_p_120_1176_p000027 [1]. Other text includes ILLUSTRATED PARTS LIST [2] and STOCK [3]."},
        ]
    }


def thresholds():
    return {
        "min_llm_drafts": 3,
        "min_final_gates": 3,
        "min_passed_final_gates": 3,
        "min_final_answers_ready_for_webui": 3,
        "min_repaired_final_answers": 3,
        "min_final_answers_with_source_truth_citations": 3,
        "min_cap_disclosures_in_final_answers": 2,
        "max_unsupported_claim_count": 0,
        "max_final_non_direct_citation_marker_count": 0,
        "max_graph_proof_authority_violations": 0,
        "max_summary_proof_authority_violations": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_no_answer_permission": True,
    }


def test_v23_repairs_v2_summary_and_nearby_context_issues():
    report = build_report(prompt_report(), draft_report(), thresholds=thresholds())
    assert report["quality_status"] == "PASS"
    assert report["draft_v2_summary_proof_violation_count"] == 1
    assert report["draft_nearby_context_overstatement_count"] == 1
    assert report["draft_non_direct_citation_marker_count"] == 2
    assert report["passed_final_gate_count"] == 3
    table = report["final_gate_records"][2]
    assert "ILLUSTRATED PARTS LIST" not in table["final_answer"]
    assert "Nearby OCR/table records" in table["final_answer"]
    assert "[2]" not in table["final_answer"]
    manual = report["final_gate_records"][1]
    assert "V2 Summary" not in manual["final_answer"]
    assert "Results were capped" in manual["final_answer"]


def test_v23_writes_report_files(tmp_path: Path):
    report = build_report(prompt_report(), draft_report(), thresholds=thresholds())
    paths = write_report_files(report, tmp_path)
    assert Path(paths["report_path"]).exists()
    assert Path(paths["records_jsonl_path"]).exists()
    assert Path(paths["final_answers_jsonl_path"]).exists()
    loaded = json.loads(Path(paths["report_path"]).read_text(encoding="utf-8"))
    assert loaded["module"] == "trace_net_e2e_live_llm_final_gate_v23"


def test_v23_markdown_mentions_repaired_drafts():
    report = build_report(prompt_report(), draft_report(), thresholds=thresholds())
    md = render_markdown(report)
    assert "Live LLM Final Gate v23" in md
    assert "repaired_from_draft" in md
    assert "draft_v2_summary_proof_violation" in md
