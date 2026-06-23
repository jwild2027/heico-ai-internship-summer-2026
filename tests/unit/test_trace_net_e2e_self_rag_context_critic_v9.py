from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_self_rag_context_critic_v9 import (
    CRITIC_NEEDS_CRAG_RETRY,
    CRITIC_NEEDS_HUMAN_REVIEW,
    CRITIC_READY,
    build_self_rag_context_critic,
    critique_context_pack,
    write_report_files,
)


def sample_pack(field_name="covered_part_number", intent="covered_part_number", *, unsafe_guidance=False):
    return {
        "context_pack_id": "dynamic_context_pack_v8_test",
        "context_pack_status": "DYNAMIC_CONTEXT_PACK_READY",
        "user_query": "Find part number 120-36834-509",
        "query_intent": intent,
        "evidence_box": {
            "authority": "source_truth_evidence_only",
            "items": [
                {
                    "evidence_id": "evidence_001",
                    "field_name": field_name,
                    "normalized_value": "120-36834-509",
                    "page_id": "t_p_120_1176_p000003",
                    "answer_authority": "source_truth_evidence_only",
                    "citation_ready": True,
                    "source_trace_ready": True,
                }
            ],
        },
        "guidance_box": {
            "authority": "guidance_only_not_source_truth",
            "items": [
                {
                    "guidance_id": "graph_001",
                    "tunnel_type": "graph_community_tunnel",
                    "authority": "graph_guidance_only_not_proof" if not unsafe_guidance else "source_truth_evidence_only",
                    "page_id": "t_p_120_1176_p000003",
                    "guidance_text": "Part family community 120-36834",
                },
                {
                    "guidance_id": "summary_001",
                    "tunnel_type": "page_summary_tunnel",
                    "authority": "guidance_only_not_source_truth",
                    "page_id": "t_p_120_1176_p000003",
                    "guidance_text": "Page summary guidance.",
                },
            ],
        },
        "rules_box": {
            "evidence_box_is_source_truth": True,
            "guidance_box_is_not_source_truth": True,
            "graph_is_not_proof_authority": True,
            "summaries_are_not_source_truth": True,
            "cite_every_factual_claim": True,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "reruns_ocr": False,
            "reruns_embeddings": False,
            "reruns_graph_build": False,
            "reruns_table_extraction": False,
        },
    }


def test_critique_context_pack_ready():
    critique = critique_context_pack(sample_pack())
    assert critique["self_rag_critic_status"] == CRITIC_READY
    assert critique["ready_for_prompt_contract"] is True
    assert critique["needs_crag_retry"] is False
    assert critique["needs_human_review"] is False


def test_critique_context_pack_detects_intent_mismatch_for_crag():
    critique = critique_context_pack(sample_pack(field_name="ipl_text", intent="covered_part_number"))
    assert critique["self_rag_critic_status"] == CRITIC_NEEDS_CRAG_RETRY
    assert critique["needs_crag_retry"] is True
    assert "intent_relevant_evidence_present" in critique["blockers"]


def test_critique_context_pack_detects_unsafe_guidance_for_human_review():
    critique = critique_context_pack(sample_pack(unsafe_guidance=True))
    assert critique["self_rag_critic_status"] == CRITIC_NEEDS_HUMAN_REVIEW
    assert critique["needs_human_review"] is True
    assert "all_guidance_is_not_source_truth" in critique["blockers"]


def test_build_report_quality_pass(tmp_path: Path):
    source = tmp_path / "context_pack.json"
    source.write_text(json.dumps({"context_packs": [sample_pack(), sample_pack(field_name="manual_page_reference", intent="manual_page_reference")]}), encoding="utf-8")
    report = build_self_rag_context_critic(
        source,
        min_context_packs=2,
        min_context_critiques=2,
        min_ready_contexts=2,
        min_contexts_with_source_truth_evidence=2,
        min_contexts_with_guidance_separation=2,
        max_human_review_count=0,
        max_graph_summary_proof_violations=0,
        require_no_answer_permission=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["ready_context_count"] == 2


def test_write_report_files(tmp_path: Path):
    source = tmp_path / "context_pack.json"
    source.write_text(json.dumps({"context_packs": [sample_pack()]}), encoding="utf-8")
    report = build_self_rag_context_critic(source)
    paths = write_report_files(report, tmp_path / "out")
    assert Path(paths["report_path"]).exists()
    assert Path(paths["critiques_jsonl_path"]).exists()
    assert Path(paths["inspect_md_path"]).exists()
