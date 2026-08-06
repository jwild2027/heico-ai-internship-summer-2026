#!/usr/bin/env python3
"""Apply TRACE-Net router/follow-up/retrieval benchmark v1 patch."""
from pathlib import Path
import shutil

patch = Path(__file__).resolve().parent
repo = Path.cwd().resolve()
if not (repo / ".git").exists():
    raise SystemExit("Run this from the repository root.")

copy_files = [
    "tiff/trace_net_follow_up_question_planner_v1.py",
    "tiff/trace_net_query_atom_router_v1.py",
    "scripts/benchmark/run_trace_net_router_followup_retrieval_benchmark_v1.py",
    "tests/data/trace_net_router_followup_question_bank_v1.json",
    "tests/unit/test_trace_net_follow_up_question_planner_v1.py",
    "tests/unit/test_trace_net_router_followup_benchmark_v1.py",
    "tests/unit/test_trace_net_followup_unified_integration_v1.py",
    "docs/trace_net/TRACE_NET_ROUTER_FOLLOWUP_RETRIEVAL_BENCHMARK_V1.md",
]
for rel in copy_files:
    src = patch / rel
    dst = repo / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print("applied", rel)

target = repo / "scripts/operations/serving/serve_trace_net_openwebui_unified_rag_v2.py"
text = target.read_text(encoding="utf-8")

old_route_kind = 'def route_kind(query: str) -> str:\n    q = query.lower()\n    has_part_word = any(term in q for term in ("part", "p/n", "pn", "part number", "item number", "nomenclature"))\n    if has_part_word and any(marker in q for marker in PARTIAL_MARKERS):\n        return "guided_discovery"\n    if any(term in set(tokenize(query)) for term in VISUAL_TERMS):\n        return "gemma_confirmed_image_visual"\n    return "normal_ask"\n'
new_route_kind = 'def route_kind(query: str) -> str:\n    """Compatibility wrapper around the deterministic query-atom router."""\n    return str(analyze_query(query)["execution_route"])\n'
if old_route_kind in text:
    text = text.replace(old_route_kind, new_route_kind, 1)
elif "Compatibility wrapper around the deterministic query-atom router" not in text:
    raise SystemExit("Could not update route_kind in unified v2.")

helper_marker = 'def fast_clarification(query: str) -> Dict[str, Any]:\n'
helper = 'def router_clarification_payload(\n    query: str,\n    router_decision: Mapping[str, Any],\n) -> Dict[str, Any]:\n    plan = (\n        router_decision.get("follow_up_plan")\n        if isinstance(router_decision.get("follow_up_plan"), Mapping)\n        else {}\n    )\n    atoms = (\n        router_decision.get("atoms")\n        if isinstance(router_decision.get("atoms"), Mapping)\n        else {}\n    )\n    return {\n        "quality_status": "PASS",\n        "intent": router_decision.get("selected_tunnel"),\n        "known_clues": dict(atoms),\n        "missing_clues": list(plan.get("follow_up_topics") or []),\n        "candidate_routes": [],\n        "strict_prefix_candidates": [],\n        "clarifying_questions": list(plan.get("clarifying_questions") or []),\n        "source_trace_status": "clarification-before-expensive-search",\n        "answer_permission": False,\n        "final_answer_allowed": False,\n        "source_truth_mutation_allowed": False,\n    }\n\n\n'
if "def router_clarification_payload(" not in text:
    if helper_marker not in text:
        raise SystemExit("Could not find fast_clarification marker.")
    text = text.replace(helper_marker, helper + helper_marker, 1)

old_guided_start = '        elif route == "guided_discovery":\n            status, downstream = http_json(\n                self.guided_base_url + "/api/trace-net/guided-discovery",\n                {"question": query, "top_k": int(payload.get("top_k") or 8), "loose_top_k": int(payload.get("loose_top_k") or 8), "include_view": False},\n                api_key=None,\n                timeout=self.timeout,\n            )\n'
new_guided_start = '        elif route == "guided_discovery":\n            tunnel = str(router_decision.get("selected_tunnel") or "")\n            if tunnel in {"descriptive_part_discovery", "fast_clarification"}:\n                status = 200\n                downstream = router_clarification_payload(query, router_decision)\n            else:\n                status, downstream = http_json(\n                    self.guided_base_url + "/api/trace-net/guided-discovery",\n                    {"question": query, "top_k": int(payload.get("top_k") or 8), "loose_top_k": int(payload.get("loose_top_k") or 8), "include_view": False},\n                    api_key=None,\n                    timeout=self.timeout,\n                )\n                if status == 200:\n                    router_questions = list(router_decision.get("clarifying_questions") or [])\n                    downstream_questions = list(downstream.get("clarifying_questions") or [])\n                    downstream["clarifying_questions"] = list(dict.fromkeys(router_questions + downstream_questions))[:5]\n'
if old_guided_start in text:
    text = text.replace(old_guided_start, new_guided_start, 1)
elif 'tunnel in {"descriptive_part_discovery", "fast_clarification"}' not in text:
    raise SystemExit("Could not update guided branch in unified v2.")

surface_marker = '        safety_rules = [e for e in engrams if str(e.get("priority")) == "hard_boundary"]\n'
surface_code = '        follow_up_questions = list(router_decision.get("clarifying_questions") or [])\n        should_surface_followups = (\n            route == "guided_discovery"\n            or (\n                route == "gemma_confirmed_image_visual"\n                and int(result.get("citation_count") or 0) == 0\n            )\n            or (\n                route == "normal_ask"\n                and (\n                    result.get("final_gate_status") == "LIVE_ORCHESTRATOR_AUDIT_ONLY"\n                    or router_decision.get("selected_tunnel") == "safety_authority_search"\n                )\n            )\n        )\n        if route != "guided_discovery" and should_surface_followups and follow_up_questions:\n            content = str(result.get("content") or "").rstrip()\n            lines = [content, "", "Helpful follow-up questions:"] if content else ["Helpful follow-up questions:"]\n            lines.extend(f"- {question}" for question in follow_up_questions[:5])\n            result["content"] = "\\n".join(lines)\n\n'
if "should_surface_followups = (" not in text:
    if surface_marker not in text:
        raise SystemExit("Could not find safety_rules marker in unified v2.")
    text = text.replace(surface_marker, surface_code + surface_marker, 1)

old_update = '            "retrieval_tunnel": router_decision.get("selected_tunnel"),\n            "query": latest,\n'
new_update = '            "retrieval_tunnel": router_decision.get("selected_tunnel"),\n            "follow_up_plan": router_decision.get("follow_up_plan"),\n            "follow_up_questions": list(router_decision.get("clarifying_questions") or []),\n            "clarification_required": bool(router_decision.get("clarification_required")),\n            "clarification_recommended": bool(router_decision.get("clarification_recommended")),\n            "query": latest,\n'
if old_update in text:
    text = text.replace(old_update, new_update, 1)
elif '"follow_up_plan": router_decision.get("follow_up_plan")' not in text:
    raise SystemExit("Could not add follow-up fields to unified v2 result.")

target.write_text(text, encoding="utf-8", newline="\n")
print("updated scripts/operations/serving/serve_trace_net_openwebui_unified_rag_v2.py")
print("status=TRACE_NET_ROUTER_FOLLOWUP_BENCHMARK_V1_PATCH_APPLIED")
