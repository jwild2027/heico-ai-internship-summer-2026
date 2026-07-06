from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import build_report, evaluate_pack


def _args(**kwargs):
    defaults = dict(
        min_context_packs=2,
        min_self_rag_evaluations=2,
        min_crag_plans=2,
        min_ready_for_llm=2,
        min_contexts_with_source_truth_evidence=2,
        min_contexts_with_graph_guidance=2,
        min_contexts_with_v2_summary_guidance=2,
        min_contexts_with_aggregation_or_cap_disclosure=1,
        max_retry_required_count=0,
        max_audit_only_count=0,
        max_graph_proof_authority_violations=0,
        max_summary_proof_authority_violations=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_no_answer_permission=True,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def sample_pack(capped=False):
    return {
        "context_pack_id": "context_pack_v19_0001",
        "query_plan_id": "query_plan_v17_0001",
        "user_query": "Find part number 120-36834-509",
        "evidence_box": {"source_truth_evidence": [{"page_id": "p1"}, {"page_id": "p2"}]},
        "guidance_box": {
            "graph_guidance": [{"community_id": "c1"}],
            "v2_summary_guidance": [{"page_id": "p1"}],
            "graph_authority": "guidance_only",
            "summary_authority": "guidance_only",
        },
        "aggregation_box": {
            "total_match_count": 20 if capped else 2,
            "returned_match_count": 2,
            "result_was_capped": capped,
            "more_results_available": capped,
        },
        "answer_rules_box": {"cite_every_factual_claim": True},
    }


def test_evaluate_pack_ready_with_cap_disclosure():
    rec = evaluate_pack(sample_pack(capped=True), 0)
    assert rec["self_rag_status"] == "CONTEXT_READY_WITH_CAP_DISCLOSURE"
    assert rec["ready_for_llm_prompt"] is True
    assert rec["retry_required"] is False
    assert rec["aggregation_or_cap_disclosure"]["more_results_available"] is True


def test_evaluate_pack_weak_without_evidence():
    pack = sample_pack()
    pack["evidence_box"] = {"source_truth_evidence": []}
    rec = evaluate_pack(pack, 0)
    assert rec["self_rag_status"] == "CONTEXT_WEAK_NEEDS_CRAG_RETRY"
    assert rec["retry_required"] is True
    assert rec["ready_for_llm_prompt"] is False


def test_build_report_passes_quality(tmp_path: Path):
    source = {
        "context_packs": [sample_pack(capped=True), sample_pack(capped=False)],
    }
    source_path = tmp_path / "v19.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    report = build_report(source_path, tmp_path / "out", _args())
    assert report["quality_status"] == "PASS"
    assert report["context_pack_count"] == 2
    assert report["ready_for_llm_count"] == 2
    assert report["contexts_with_aggregation_or_cap_disclosure_count"] >= 1


def test_graph_proof_authority_violation_blocks():
    pack = sample_pack()
    pack["guidance_box"]["graph_authority"] = "proof_authority"
    rec = evaluate_pack(pack, 0)
    assert rec["audit_only"] is True
    assert rec["graph_proof_authority_violation"] is True
