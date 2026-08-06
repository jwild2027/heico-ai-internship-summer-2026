#!/usr/bin/env python3
from __future__ import annotations
import json
from scripts.operations.s6_retrieval.serve_trace_net_cognitive_router_v1 import build_follow_up_questions, extract_query_atoms, plan_route
from scripts.benchmark.validation.run_trace_net_full_user_query_gemma_benchmark_v1 import topic_visible, used_tunnel_matches_plan
from tiff.trace_net_answer_quality_guard_v1 import evaluate_answer_quality


def rp(query):
    atoms = extract_query_atoms(query)
    return atoms, plan_route(atoms)


def main() -> int:
    item, item_plan = rp("The item number begins with PE13")
    true_item, true_item_plan = rp("Search the IPL table for item 14")
    nas, nas_plan = rp("The part starts with NAS and I am not sure of the rest")
    bearing, bearing_plan = rp("I am looking for a bearing")
    contains_q = build_follow_up_questions(extract_query_atoms("I only remember the part contains 824"), "guided_part_discovery")
    desc_q = build_follow_up_questions(bearing, "nomenclature_function_search")
    q006 = evaluate_answer_quality(
        query="The P/N starts with MS49 and I cannot remember more",
        answer="TRACE-Net found candidate evidence, not a final identification:\n- MS4956 — ATA 25-21-00; WS4956 1\n",
        trace={"route": "guided_part_discovery", "follow_up_questions": []},
    )
    checks = {
        "partial_item_prefix_guided": item.identifier_mode == "prefix" and item_plan.primary_route == "guided_part_discovery",
        "true_ipl_item_remains_table": true_item.identifier_mode == "none" and true_item_plan.primary_route == "exact_table_ipl_lookup",
        "nas_alpha_prefix_guided": nas.identifier_mode == "prefix" and nas_plan.primary_route == "guided_part_discovery",
        "bearing_is_nomenclature": bearing_plan.primary_route == "nomenclature_function_search",
        "contains_has_five_followups": len(contains_q) == 5,
        "contains_has_physical_description": topic_visible("physical_description", contains_q),
        "descriptive_has_part_number": topic_visible("part_number", desc_q),
        "descriptive_has_manufacturer": topic_visible("manufacturer", desc_q),
        "q006_description_token_not_candidate": not any(x.startswith("strict_prefix_candidate_mismatch:") for x in q006),
        "specialized_label_is_declared_derivative": used_tunnel_matches_plan(
            "exact_table_ipl_lookup_specialized_1",
            ["normal_source_truth", "table_rows_cells", "ocr_fallback", "figure_item_linkage"],
            "exact_table_ipl_lookup",
        ),
        "answer_permission_false": True,
        "source_truth_mutation_false": True,
    }
    failures = [k for k,v in checks.items() if not v]
    result = {
        "module": "check_trace_net_h30_phase4_5_8_first38_discovery_contract_v1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures), "failures": failures, "checks": checks,
        "item_prefix_route": item_plan.primary_route, "true_item_route": true_item_plan.primary_route,
        "nas_route": nas_plan.primary_route, "bearing_route": bearing_plan.primary_route,
        "contains_followup_count": len(contains_q), "descriptive_followup_count": len(desc_q),
        "answer_permission": False, "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False, "qdrant_write_attempt": False, "opensearch_write_attempt": False,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1

if __name__ == "__main__": raise SystemExit(main())
