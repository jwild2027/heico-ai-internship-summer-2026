from __future__ import annotations

import argparse
import json
from pathlib import Path


def sample_context_pack_report():
    pack = {
        "context_pack_id": "dynamic_context_pack_v8_0001",
        "context_pack_status": "DYNAMIC_CONTEXT_PACK_READY",
        "user_query": "Find part number 120-36834-509",
        "query_intent": "covered_part_number",
        "evidence_box": {
            "authority": "source_truth_evidence_only",
            "items": [
                {
                    "evidence_id": "evidence_001",
                    "rank": 1,
                    "page_id": "t_p_120_1176_p000003",
                    "field_name": "covered_part_number",
                    "normalized_value": "120-36834-509",
                    "citation_ready": True,
                    "source_trace_ready": True,
                    "answer_authority": "source_truth_evidence_only",
                    "source_tunnel": "table_exact_search_tunnel",
                    "total_tunnel_score": 319,
                }
            ],
        },
        "guidance_box": {
            "authority": "guidance_only_not_source_truth",
            "items": [
                {
                    "guidance_id": "page_summary_t_p_120_1176_p000003",
                    "page_id": "t_p_120_1176_p000003",
                    "tunnel_type": "page_summary_tunnel",
                    "authority": "guidance_only_not_source_truth",
                    "guidance_text": "This page appears to be a parts list or applicability section.",
                },
                {
                    "guidance_id": "graph_community_t_p_120_1176_p000003_1",
                    "page_id": "t_p_120_1176_p000003",
                    "tunnel_type": "graph_community_tunnel",
                    "authority": "graph_guidance_only_not_proof",
                    "guidance_text": "Part family community 120-36834.",
                },
            ],
        },
        "rules_box": {
            "evidence_box_is_source_truth": True,
            "guidance_box_is_not_source_truth": True,
            "graph_is_not_proof_authority": True,
            "summaries_are_not_source_truth": True,
            "cite_every_factual_claim": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        },
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }
    return {"quality_status": "PASS", "context_packs": [pack]}


def sample_self_rag_report():
    critique = {
        "context_pack_id": "dynamic_context_pack_v8_0001",
        "user_query": "Find part number 120-36834-509",
        "query_intent": "covered_part_number",
        "self_rag_critic_status": "SELF_RAG_CONTEXT_READY",
        "needs_crag_retry": False,
        "needs_human_review": False,
        "source_truth_evidence_count": 1,
        "citation_ready_evidence_count": 1,
        "source_trace_ready_evidence_count": 1,
        "intent_relevant_evidence_count": 1,
        "graph_summary_proof_violation_count": 0,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }
    return {"quality_status": "PASS", "critiques": [critique]}


def sample_crag_report(status="CRAG_NO_RETRY_NEEDED"):
    plan = {
        "context_pack_id": "dynamic_context_pack_v8_0001",
        "user_query": "Find part number 120-36834-509",
        "query_intent": "covered_part_number",
        "crag_plan_status": status,
        "needs_retry": False,
        "needs_human_review": False,
        "graph_summary_proof_violation_count": 0,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }
    return {"quality_status": "PASS", "crag_plans": [plan]}


def quality_args(**overrides):
    values = {
        "min_context_packs": 1,
        "min_prompt_contracts": 1,
        "min_ready_prompt_contracts": 1,
        "min_total_prompt_messages": 3,
        "min_contracts_with_source_truth_evidence": 1,
        "min_contracts_with_guidance_box": 1,
        "min_contracts_with_self_rag_ready": 1,
        "min_contracts_with_crag_no_retry": 1,
        "min_contracts_with_graph_or_summary_guidance": 1,
        "max_graph_summary_proof_violations": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_no_answer_permission": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_build_prompt_contract_report_ready():
    from tiff.trace_net_e2e_llm_prompt_contract_v11 import build_llm_prompt_contract_report

    report = build_llm_prompt_contract_report(sample_context_pack_report(), sample_self_rag_report(), sample_crag_report())

    assert report["quality_status"] == "PASS"
    assert report["summary"]["prompt_contract_count"] == 1
    assert report["summary"]["ready_prompt_contract_count"] == 1
    prompt = report["prompt_contracts"][0]
    assert prompt["prompt_contract_status"] == "LLM_PROMPT_CONTRACT_READY"
    assert prompt["ready_for_reasoned_response_draft"] is True
    assert prompt["message_count"] == 3


def test_prompt_text_separates_evidence_guidance_and_rules():
    from tiff.trace_net_e2e_llm_prompt_contract_v11 import build_llm_prompt_contract_report

    prompt = build_llm_prompt_contract_report(sample_context_pack_report(), sample_self_rag_report(), sample_crag_report())["prompt_contracts"][0]
    text = prompt["prompt_text"]

    assert "SOURCE-TRUTH EVIDENCE" in text
    assert "GUIDANCE ONLY" in text
    assert "ANSWER RULES" in text
    assert "120-36834-509" in text
    assert "Graph" not in prompt["messages"][0]["content"] or "not proof" in text
    assert prompt["prompt_policy"]["llm_may_answer_from_guidance_only"] is False
    assert prompt["prompt_policy"]["graph_is_not_proof_authority"] is True


def test_evaluate_quality_passes_for_ready_report():
    from tiff.trace_net_e2e_llm_prompt_contract_v11 import build_llm_prompt_contract_report, evaluate_quality

    report = build_llm_prompt_contract_report(sample_context_pack_report(), sample_self_rag_report(), sample_crag_report())
    status, checks = evaluate_quality(report, quality_args())

    assert status == "PASS"
    assert all(check["passed"] for check in checks)


def test_crag_retry_makes_prompt_not_ready():
    from tiff.trace_net_e2e_llm_prompt_contract_v11 import build_llm_prompt_contract_report

    crag = sample_crag_report(status="CRAG_RETRY_PLAN_READY")
    crag["crag_plans"][0]["needs_retry"] = True
    report = build_llm_prompt_contract_report(sample_context_pack_report(), sample_self_rag_report(), crag)
    prompt = report["prompt_contracts"][0]

    assert prompt["ready_for_reasoned_response_draft"] is False
    assert prompt["source_crag_plan_status"] == "CRAG_RETRY_PLAN_READY"


def test_write_report_files(tmp_path: Path):
    from tiff.trace_net_e2e_llm_prompt_contract_v11 import build_llm_prompt_contract_report, write_report_files

    report = build_llm_prompt_contract_report(sample_context_pack_report(), sample_self_rag_report(), sample_crag_report())
    paths = write_report_files(report, tmp_path)

    assert Path(paths["report_path"]).exists()
    assert Path(paths["prompts_jsonl_path"]).exists()
    assert Path(paths["messages_jsonl_path"]).exists()
    assert Path(paths["inspect_md_path"]).exists()
    assert "TRACE-Net E2E LLM Prompt Contract v11" in Path(paths["inspect_md_path"]).read_text(encoding="utf-8")


def test_script_build_and_check(tmp_path: Path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    context_path = tmp_path / "context.json"
    self_path = tmp_path / "self.json"
    crag_path = tmp_path / "crag.json"
    out_dir = tmp_path / "out"
    context_path.write_text(json.dumps(sample_context_pack_report()), encoding="utf-8")
    self_path.write_text(json.dumps(sample_self_rag_report()), encoding="utf-8")
    crag_path.write_text(json.dumps(sample_crag_report()), encoding="utf-8")

    build = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "build_trace_net_e2e_llm_prompt_contract_v11.py"),
            "--dynamic-context-pack",
            str(context_path),
            "--self-rag-context-critic",
            str(self_path),
            "--crag-retrieval-corrector",
            str(crag_path),
            "--output-dir",
            str(out_dir),
            "--min-context-packs",
            "1",
            "--min-prompt-contracts",
            "1",
            "--min-ready-prompt-contracts",
            "1",
            "--min-total-prompt-messages",
            "3",
            "--min-contracts-with-source-truth-evidence",
            "1",
            "--min-contracts-with-guidance-box",
            "1",
            "--min-contracts-with-self-rag-ready",
            "1",
            "--min-contracts-with-crag-no-retry",
            "1",
            "--min-contracts-with-graph-or-summary-guidance",
            "1",
            "--max-graph-summary-proof-violations",
            "0",
            "--max-answer-permission-count",
            "0",
            "--max-source-truth-mutation-allowed",
            "0",
            "--require-no-answer-permission",
            "--quality",
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr + build.stdout
    report_path = out_dir / "trace_net_e2e_llm_prompt_contract_v11.json"
    assert report_path.exists()

    check = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "check_trace_net_e2e_llm_prompt_contract_v11_quality.py"),
            "--report-path",
            str(report_path),
            "--min-context-packs",
            "1",
            "--min-prompt-contracts",
            "1",
            "--min-ready-prompt-contracts",
            "1",
            "--min-total-prompt-messages",
            "3",
            "--min-contracts-with-source-truth-evidence",
            "1",
            "--min-contracts-with-guidance-box",
            "1",
            "--min-contracts-with-self-rag-ready",
            "1",
            "--min-contracts-with-crag-no-retry",
            "1",
            "--min-contracts-with-graph-or-summary-guidance",
            "1",
            "--max-graph-summary-proof-violations",
            "0",
            "--max-answer-permission-count",
            "0",
            "--max-source-truth-mutation-allowed",
            "0",
            "--require-no-answer-permission",
            "--write-json",
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert check.returncode == 0, check.stderr + check.stdout
