from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tiff.trace_net_e2e_crag_retrieval_corrector_v10 import (
    NO_RETRY_STATUS,
    RETRY_READY_STATUS,
    build_crag_corrector_report,
    evaluate_quality,
)


def sample_ready_critic():
    return {
        "quality_status": "PASS",
        "critiques": [
            {
                "context_pack_id": "ctx_001",
                "user_query": "Find part number 120-36834-509",
                "query_intent": "covered_part_number",
                "self_rag_critic_status": "SELF_RAG_CONTEXT_READY",
                "evidence_item_count": 3,
                "source_truth_evidence_count": 3,
                "citation_ready_evidence_count": 3,
                "source_trace_ready_evidence_count": 3,
                "intent_relevant_evidence_count": 3,
                "guidance_item_count": 2,
                "safe_guidance_item_count": 2,
                "graph_summary_proof_violation_count": 0,
                "needs_crag_retry": False,
                "needs_human_review": False,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "findings": [],
            }
        ],
    }


def sample_weak_critic():
    return {
        "quality_status": "PASS",
        "critiques": [
            {
                "context_pack_id": "ctx_weak",
                "user_query": "What maintenance manual pages mention covered part numbers?",
                "query_intent": "covered_part_number",
                "self_rag_critic_status": "SELF_RAG_CONTEXT_NEEDS_CRAG_RETRY",
                "evidence_item_count": 3,
                "source_truth_evidence_count": 3,
                "citation_ready_evidence_count": 3,
                "source_trace_ready_evidence_count": 3,
                "intent_relevant_evidence_count": 0,
                "guidance_item_count": 2,
                "safe_guidance_item_count": 2,
                "graph_summary_proof_violation_count": 0,
                "needs_crag_retry": True,
                "needs_human_review": False,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "findings": [
                    {
                        "name": "intent_relevant_evidence_present",
                        "passed": False,
                        "severity": "blocker",
                    }
                ],
            }
        ],
    }


def test_build_crag_report_no_retry_ready():
    report = build_crag_corrector_report(sample_ready_critic(), source_path="critic.json")
    assert report["summary"]["crag_plan_count"] == 1
    assert report["summary"]["no_retry_needed_count"] == 1
    assert report["summary"]["retry_required_plan_count"] == 0
    assert report["crag_plans"][0]["crag_plan_status"] == NO_RETRY_STATUS
    assert report["crag_plans"][0]["corrective_actions"][0]["action_type"] == "no_retry_required"
    assert report["summary"]["answer_permission_count"] == 0
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0


def test_build_crag_report_retry_ready_for_intent_mismatch():
    report = build_crag_corrector_report(sample_weak_critic(), source_path="critic.json")
    plan = report["crag_plans"][0]
    assert plan["crag_plan_status"] == RETRY_READY_STATUS
    assert plan["needs_retry"] is True
    assert any(a["action_type"] == "route_and_field_correction" for a in plan["corrective_actions"])
    assert "query_intent_mismatch_or_wrong_field" in plan["retry_reasons"]
    assert report["summary"]["corrective_action_count"] >= 1


def test_quality_pass_for_ready_report():
    report = build_crag_corrector_report(sample_ready_critic(), source_path="critic.json")
    class Args:
        min_context_critiques = 1
        min_crag_plans = 1
        min_ready_crag_plans = 1
        min_no_retry_needed_count = 1
        min_corrective_actions = 0
        max_retry_required_plan_count = 0
        max_human_review_plan_count = 0
        max_unresolved_plan_count = 0
        max_graph_summary_proof_violations = 0
        max_answer_permission_count = 0
        max_source_truth_mutation_allowed = 0
        require_no_answer_permission = True
    status, checks = evaluate_quality(report, Args())
    assert status == "PASS"
    assert all(c["passed"] for c in checks)


def test_build_and_check_scripts(tmp_path: Path):
    critic_path = tmp_path / "critic.json"
    out_dir = tmp_path / "out"
    critic_path.write_text(json.dumps(sample_ready_critic()), encoding="utf-8")

    build_cmd = [
        sys.executable,
        "scripts/benchmark/validation/build_trace_net_e2e_crag_retrieval_corrector_v10.py",
        "--self-rag-context-critic",
        str(critic_path),
        "--output-dir",
        str(out_dir),
        "--min-context-critiques",
        "1",
        "--min-crag-plans",
        "1",
        "--min-ready-crag-plans",
        "1",
        "--min-no-retry-needed-count",
        "1",
        "--max-retry-required-plan-count",
        "0",
        "--max-human-review-plan-count",
        "0",
        "--max-unresolved-plan-count",
        "0",
        "--require-no-answer-permission",
        "--quality",
    ]
    subprocess.run(build_cmd, check=True, cwd=Path.cwd())

    report_path = out_dir / "trace_net_e2e_crag_retrieval_corrector_v10.json"
    assert report_path.exists()

    check_cmd = [
        sys.executable,
        "scripts/benchmark/validation/check_trace_net_e2e_crag_retrieval_corrector_v10_quality.py",
        "--report-path",
        str(report_path),
        "--min-context-critiques",
        "1",
        "--min-crag-plans",
        "1",
        "--min-ready-crag-plans",
        "1",
        "--min-no-retry-needed-count",
        "1",
        "--max-retry-required-plan-count",
        "0",
        "--max-human-review-plan-count",
        "0",
        "--max-unresolved-plan-count",
        "0",
        "--require-no-answer-permission",
        "--write-json",
    ]
    subprocess.run(check_cmd, check=True, cwd=Path.cwd())


def test_weak_report_quality_can_require_corrective_action():
    report = build_crag_corrector_report(sample_weak_critic(), source_path="critic.json")
    class Args:
        min_context_critiques = 1
        min_crag_plans = 1
        min_ready_crag_plans = 1
        min_no_retry_needed_count = 0
        min_corrective_actions = 1
        max_retry_required_plan_count = 1
        max_human_review_plan_count = 0
        max_unresolved_plan_count = 0
        max_graph_summary_proof_violations = 0
        max_answer_permission_count = 0
        max_source_truth_mutation_allowed = 0
        require_no_answer_permission = True
    status, checks = evaluate_quality(report, Args())
    assert status == "PASS"
    assert all(c["passed"] for c in checks)
