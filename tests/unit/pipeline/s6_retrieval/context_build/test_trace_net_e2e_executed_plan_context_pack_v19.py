from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_e2e_executed_plan_context_pack_v19 import build_and_write, build_report, evaluate_quality


def sample_v18_report():
    records = []
    for i in range(1, 6):
        evidence = [
            {
                "evidence_id": f"ev_{i}_{j}",
                "page_id": f"t_p_120_1176_p{j:06d}",
                "field_name": "covered_part_number" if j % 2 else "ipl_part_number",
                "normalized_value": f"120-36833-50{j}",
                "citation_ready": True,
                "source_trace_ready": True,
                "leiden_community_id": f"community_{i}",
            }
            for j in range(1, 4)
        ]
        records.append(
            {
                "execution_id": f"execution_{i}",
                "query_plan_id": f"query_plan_v17_{i:04d}",
                "user_query": f"Find part number 120-36833-50{i}",
                "query_intent": "part_number",
                "source_truth_evidence": evidence,
                "graph_guidance": [
                    {
                        "guidance_id": f"graph_{i}",
                        "leiden_community_id": f"community_{i}",
                        "path": ["seed_page", "same_leiden_community"],
                        "proof_authority": False,
                    }
                ],
                "v2_summary_guidance": [
                    {
                        "summary_id": f"summary_{i}",
                        "page_id": f"t_p_120_1176_p{i:06d}",
                        "summary": "Synthetic page context.",
                        "proof_authority": False,
                    }
                ],
                "aggregation": {
                    "total_match_count": 25 if i == 1 else 3,
                    "returned_match_count": 3,
                    "result_was_capped": i == 1,
                    "more_results_available": i == 1,
                    "high_degree_node_detected": i == 1,
                    "group_counts": {"by_leiden_community": {f"community_{i}": 3}},
                },
            }
        )
    return {"module": "trace_net_e2e_dynamic_plan_executor_v18", "execution_records": records}


def quality_args():
    return argparse.Namespace(
        min_context_packs=5,
        min_ready_context_packs=5,
        min_source_truth_evidence=10,
        min_packs_with_evidence_box=5,
        min_packs_with_guidance_box=5,
        min_packs_with_graph_guidance=5,
        min_packs_with_v2_summary_guidance=5,
        min_packs_with_answer_rules=5,
        min_packs_with_aggregation_or_cap_disclosure=5,
        max_graph_proof_authority_violations=0,
        max_summary_proof_authority_violations=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_no_answer_permission=True,
    )


def test_v19_builds_context_packs_with_guidance_and_source_truth():
    report = build_report(sample_v18_report(), top_k=10, high_degree_threshold=10, max_pages_per_community=25)
    assert report["context_pack_count"] == 5
    assert report["ready_context_pack_count"] == 5
    assert report["total_source_truth_evidence_count"] == 15
    assert report["packs_with_graph_guidance_count"] == 5
    assert report["packs_with_v2_summary_guidance_count"] == 5
    assert report["graph_proof_authority_violation_count"] == 0
    assert report["summary_proof_authority_violation_count"] == 0
    assert report["context_packs"][0]["aggregation_box"]["result_was_capped"] is True
    assert report["context_packs"][0]["answer_rules_box"]["disclose_capped_results"] is True


def test_v19_quality_passes_for_sample_report():
    report = build_report(sample_v18_report(), top_k=10, high_degree_threshold=10, max_pages_per_community=25)
    status, checks = evaluate_quality(report, quality_args())
    assert status == "PASS"
    assert all(c["passed"] for c in checks)


def test_v19_detects_graph_proof_violation():
    data = sample_v18_report()
    data["execution_records"][0]["graph_guidance"][0]["proof_authority"] = True
    report = build_report(data, top_k=10, high_degree_threshold=10, max_pages_per_community=25)
    assert report["graph_proof_authority_violation_count"] == 1
    status, _ = evaluate_quality(report, quality_args())
    assert status == "FAIL"


def test_v19_writes_report_files(tmp_path: Path):
    src = tmp_path / "v18.json"
    src.write_text(json.dumps(sample_v18_report()), encoding="utf-8")
    out = tmp_path / "out"
    report = build_and_write(src, out, quality_args=quality_args())
    assert report["quality_status"] == "PASS"
    assert (out / "trace_net_e2e_executed_plan_context_pack_v19.json").exists()
    assert (out / "trace_net_e2e_executed_plan_context_pack_records_v19.jsonl").exists()
    assert (out / "trace_net_e2e_executed_plan_context_pack_evidence_v19.jsonl").exists()
    assert (out / "trace_net_e2e_executed_plan_context_pack_v19.md").exists()
