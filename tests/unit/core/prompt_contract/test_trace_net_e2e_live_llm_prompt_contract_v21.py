from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_live_llm_prompt_contract_v21 import build_report, render_markdown, write_report_files


def sample_context_pack_report(count: int = 5):
    packs = []
    for i in range(1, count + 1):
        packs.append(
            {
                "context_pack_id": f"pack_{i}",
                "user_query": f"Find part number 120-0000{i}-001",
                "evidence_box": {
                    "items": [
                        {
                            "page_id": f"p{i:04d}",
                            "field_name": "covered_part_number",
                            "normalized_value": f"120-0000{i}-001",
                            "citation_id": "[1]",
                            "source_trace_ready": True,
                        }
                    ],
                    "item_count": 1,
                },
                "guidance_box": {
                    "graph_guidance": [
                        {"community_id": f"c{i}", "authority": "guidance_only", "path": ["seed", "neighbor"]}
                    ],
                    "v2_summary_guidance": [
                        {"page_id": f"p{i:04d}", "summary": "covered parts page", "authority": "guidance_only"}
                    ],
                },
                "aggregation_box": {
                    "total_match_count": 20,
                    "returned_match_count": 1,
                    "result_was_capped": True,
                    "more_results_available": True,
                    "drilldown_options": ["document", "field", "community"],
                },
                "answer_rules_box": {"cite_source_truth_only": True, "disclose_caps": True},
            }
        )
    return {"context_packs": packs}


def sample_evaluator_report(count: int = 5):
    return {
        "self_rag_evaluations": [
            {
                "context_pack_id": f"pack_{i}",
                "context_status": "CONTEXT_READY_WITH_CAP_DISCLOSURE",
                "ready_for_llm": True,
                "retry_required": False,
                "crag_status": "NO_RETRY_NEEDED",
            }
            for i in range(1, count + 1)
        ]
    }


def thresholds():
    return {
        "min_context_packs": 5,
        "min_prompt_contracts": 5,
        "min_ready_prompt_contracts": 5,
        "min_total_prompt_messages": 15,
        "min_contracts_with_source_truth_evidence": 5,
        "min_contracts_with_graph_guidance": 5,
        "min_contracts_with_v2_summary_guidance": 5,
        "min_contracts_with_aggregation_or_cap_disclosure": 5,
        "min_contracts_with_self_rag_ready": 5,
        "min_contracts_with_crag_no_retry": 5,
        "min_contracts_with_answer_rules": 5,
        "max_graph_proof_authority_violations": 0,
        "max_summary_proof_authority_violations": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_no_answer_permission": True,
    }


def test_v21_builds_prompt_contracts_ready_for_llm():
    report = build_report(sample_context_pack_report(), sample_evaluator_report(), thresholds())
    assert report["quality_status"] == "PASS"
    assert report["ready_prompt_contract_count"] == 5
    assert report["total_prompt_message_count"] == 15
    first = report["prompt_contracts"][0]
    assert first["messages"][0]["role"] == "system"
    assert "SOURCE-TRUTH EVIDENCE" in first["messages"][2]["content"]
    assert "GRAPH / LEIDEN GUIDANCE" in first["messages"][2]["content"]
    assert "V2 SUMMARY GUIDANCE" in first["messages"][2]["content"]


def test_v21_blocks_graph_proof_authority_violation():
    ctx = sample_context_pack_report()
    ctx["context_packs"][0]["guidance_box"]["graph_guidance"][0]["authority"] = "proof"
    report = build_report(ctx, sample_evaluator_report(), thresholds())
    assert report["quality_status"] == "FAIL"
    assert report["graph_proof_authority_violation_count"] == 1
    assert report["ready_prompt_contract_count"] == 4


def test_v21_missing_evidence_needs_repair():
    ctx = sample_context_pack_report()
    ctx["context_packs"][0]["evidence_box"]["items"] = []
    report = build_report(ctx, sample_evaluator_report(), thresholds())
    assert report["quality_status"] == "FAIL"
    assert report["contracts_with_source_truth_evidence_count"] == 4


def test_v21_writes_report_files(tmp_path: Path):
    report = build_report(sample_context_pack_report(), sample_evaluator_report(), thresholds())
    paths = write_report_files(report, tmp_path)
    assert Path(paths["report_path"]).exists()
    assert Path(paths["prompts_jsonl_path"]).exists()
    assert Path(paths["messages_jsonl_path"]).exists()
    assert Path(paths["inspect_md_path"]).exists()
    loaded = json.loads(Path(paths["report_path"]).read_text(encoding="utf-8"))
    assert loaded["module"] == "trace_net_e2e_live_llm_prompt_contract_v21"


def test_v21_markdown_mentions_contract():
    report = build_report(sample_context_pack_report(), sample_evaluator_report(), thresholds())
    md = render_markdown(report)
    assert "Live LLM Prompt Contract v21" in md
    assert "Source-truth evidence" in md


def test_v21_1_maps_v20_self_rag_crag_records_and_includes_status():
    ctx = sample_context_pack_report(count=1)
    evaluator = {
        "self_rag_crag_records": [
            {
                "context_pack_id": "pack_1",
                "self_rag_status": "CONTEXT_READY_WITH_CAP_DISCLOSURE",
                "crag_status": "NO_RETRY_NEEDED",
                "ready_for_llm_prompt": True,
                "retry_required": False,
                "aggregation_or_cap_disclosure": {"result_was_capped": True, "more_results_available": True},
                "limitations": ["Results are capped; disclose totals and drilldowns."],
            }
        ]
    }
    th = thresholds()
    th.update({
        "min_context_packs": 1,
        "min_prompt_contracts": 1,
        "min_ready_prompt_contracts": 1,
        "min_total_prompt_messages": 3,
        "min_contracts_with_source_truth_evidence": 1,
        "min_contracts_with_graph_guidance": 1,
        "min_contracts_with_v2_summary_guidance": 1,
        "min_contracts_with_aggregation_or_cap_disclosure": 1,
        "min_contracts_with_self_rag_ready": 1,
        "min_contracts_with_crag_no_retry": 1,
        "min_contracts_with_answer_rules": 1,
    })
    report = build_report(ctx, evaluator, th)
    assert report["quality_status"] == "PASS"
    content = report["prompt_contracts"][0]["messages"][2]["content"]
    assert "SELF-RAG / CRAG STATUS" in content
    assert "CONTEXT_READY_WITH_CAP_DISCLOSURE" in content
    assert "NO_RETRY_NEEDED" in content
    assert "requires_cap_disclosure" in content


def test_v21_1_deduplicates_repeated_source_truth_evidence():
    ctx = sample_context_pack_report(count=1)
    ctx["context_packs"][0]["user_query"] = "Where is manual reference 25-21-00 used?"
    ctx["context_packs"][0]["evidence_box"]["items"] = [
        {"page_id": "p0005", "field_name": "manual_page_reference", "normalized_value": "25-21-00"},
        {"page_id": "p0005", "field_name": "manual_page_reference", "normalized_value": "25-21-00"},
        {"page_id": "p0005", "field_name": "manual_page_reference", "normalized_value": "25-21-00"},
    ]
    th = thresholds()
    th.update({
        "min_context_packs": 1,
        "min_prompt_contracts": 1,
        "min_ready_prompt_contracts": 1,
        "min_total_prompt_messages": 3,
        "min_contracts_with_source_truth_evidence": 1,
        "min_contracts_with_graph_guidance": 1,
        "min_contracts_with_v2_summary_guidance": 1,
        "min_contracts_with_aggregation_or_cap_disclosure": 1,
        "min_contracts_with_self_rag_ready": 1,
        "min_contracts_with_crag_no_retry": 1,
        "min_contracts_with_answer_rules": 1,
    })
    report = build_report(ctx, {"self_rag_crag_records": [{"context_pack_id": "pack_1", "ready_for_llm_prompt": True, "retry_required": False}]}, th)
    contract = report["prompt_contracts"][0]
    assert contract["evidence_item_count"] == 1
    assert contract["collapsed_duplicate_record_count"] == 2
    content = contract["messages"][2]["content"]
    assert "occurrence_count=3" in content
    assert "collapsed_duplicate_record_count" in content


def test_v21_1_separates_exact_table_text_from_nearby_ocr_context():
    ctx = sample_context_pack_report(count=1)
    ctx["context_packs"][0]["user_query"] = "Search table text MAINTENANCE MANUAL WITH"
    ctx["context_packs"][0]["evidence_box"]["items"] = [
        {"page_id": "p0027", "field_name": "ipl_text", "normalized_value": "MAINTENANCE MANUAL WITH"},
        {"page_id": "p0027", "field_name": "ipl_text", "normalized_value": "evsevine| PER"},
        {"page_id": "p0027", "field_name": "ipl_text", "normalized_value": "NUMBER en"},
    ]
    th = thresholds()
    th.update({
        "min_context_packs": 1,
        "min_prompt_contracts": 1,
        "min_ready_prompt_contracts": 1,
        "min_total_prompt_messages": 3,
        "min_contracts_with_source_truth_evidence": 1,
        "min_contracts_with_graph_guidance": 1,
        "min_contracts_with_v2_summary_guidance": 1,
        "min_contracts_with_aggregation_or_cap_disclosure": 1,
        "min_contracts_with_self_rag_ready": 1,
        "min_contracts_with_crag_no_retry": 1,
        "min_contracts_with_answer_rules": 1,
    })
    report = build_report(ctx, {"self_rag_crag_records": [{"context_pack_id": "pack_1", "ready_for_llm_prompt": True, "retry_required": False}]}, th)
    contract = report["prompt_contracts"][0]
    assert contract["direct_source_truth_evidence_count"] == 1
    assert contract["nearby_source_truth_context_count"] == 2
    content = contract["messages"][2]["content"]
    assert "SOURCE-TRUTH EVIDENCE (direct proof authority" in content
    assert "NEARBY SOURCE-TRUTH CONTEXT" in content
    assert "MAINTENANCE MANUAL WITH" in content
    assert "evsevine| PER" in content


def test_v21_2_does_not_promote_tiny_ocr_fragments_to_direct_evidence():
    ctx = sample_context_pack_report(count=1)
    ctx["context_packs"][0]["user_query"] = "Search table text MAINTENANCE MANUAL WITH"
    ctx["context_packs"][0]["evidence_box"]["items"] = [
        {"page_id": "p0027", "field_name": "ipl_text", "normalized_value": "MAINTENANCE MANUAL WITH"},
        {"page_id": "p0027", "field_name": "ipl_text", "normalized_value": "i", "occurrence_count": 2},
        {"page_id": "p0027", "field_name": "ipl_text", "normalized_value": "|"},
    ]
    th = thresholds()
    th.update({
        "min_context_packs": 1,
        "min_prompt_contracts": 1,
        "min_ready_prompt_contracts": 1,
        "min_total_prompt_messages": 3,
        "min_contracts_with_source_truth_evidence": 1,
        "min_contracts_with_graph_guidance": 1,
        "min_contracts_with_v2_summary_guidance": 1,
        "min_contracts_with_aggregation_or_cap_disclosure": 1,
        "min_contracts_with_self_rag_ready": 1,
        "min_contracts_with_crag_no_retry": 1,
        "min_contracts_with_answer_rules": 1,
    })
    report = build_report(ctx, {"self_rag_crag_records": [{"context_pack_id": "pack_1", "ready_for_llm_prompt": True, "retry_required": False}]}, th)
    contract = report["prompt_contracts"][0]
    assert contract["direct_source_truth_evidence_count"] == 1
    assert contract["nearby_source_truth_context_count"] == 2
    content = contract["messages"][2]["content"]
    direct_block = content.split("NEARBY SOURCE-TRUTH CONTEXT")[0]
    assert "MAINTENANCE MANUAL WITH" in direct_block
    assert "value=i" not in direct_block
    assert "value=|" not in direct_block
    assert "value=i occurrence_count=2" in content


def test_v21_2_hygiene_counts_preserve_precollapsed_occurrence_count():
    ctx = sample_context_pack_report(count=1)
    ctx["context_packs"][0]["user_query"] = "Where is manual reference 25-21-00 used?"
    ctx["context_packs"][0]["evidence_box"]["items"] = [
        {"page_id": "p0005", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "occurrence_count": 10},
    ]
    th = thresholds()
    th.update({
        "min_context_packs": 1,
        "min_prompt_contracts": 1,
        "min_ready_prompt_contracts": 1,
        "min_total_prompt_messages": 3,
        "min_contracts_with_source_truth_evidence": 1,
        "min_contracts_with_graph_guidance": 1,
        "min_contracts_with_v2_summary_guidance": 1,
        "min_contracts_with_aggregation_or_cap_disclosure": 1,
        "min_contracts_with_self_rag_ready": 1,
        "min_contracts_with_crag_no_retry": 1,
        "min_contracts_with_answer_rules": 1,
    })
    report = build_report(ctx, {"self_rag_crag_records": [{"context_pack_id": "pack_1", "ready_for_llm_prompt": True, "retry_required": False}]}, th)
    contract = report["prompt_contracts"][0]
    assert contract["collapsed_duplicate_record_count"] == 9
    content = contract["messages"][2]["content"]
    assert '"original_evidence_record_count": 10' in content
    assert '"collapsed_duplicate_record_count": 9' in content
    assert "occurrence_count=10" in content
