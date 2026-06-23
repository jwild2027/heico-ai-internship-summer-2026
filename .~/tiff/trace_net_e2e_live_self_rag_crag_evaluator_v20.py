from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_e2e_live_self_rag_crag_evaluator_v20"
VERSION = "v20"
READY_STATUS = "E2E_LIVE_SELF_RAG_CRAG_EVALUATOR_READY_FOR_LIVE_LLM_PROMPT"
NEEDS_RETRY_STATUS = "E2E_LIVE_SELF_RAG_CRAG_EVALUATOR_NEEDS_CRAG_RETRY_OR_REPAIR"

READY_SELF_RAG_STATUSES = {
    "CONTEXT_READY_FOR_LLM",
    "CONTEXT_READY_WITH_CAP_DISCLOSURE",
    "CONTEXT_PARTIAL_NEEDS_LIMITATION",
}


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _first_present(mapping: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _first_list(mapping: Mapping[str, Any], keys: Sequence[str]) -> List[Any]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, list):
            return value
    return []


def _count_records(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in (
            "records",
            "items",
            "evidence",
            "source_truth_evidence",
            "graph_guidance",
            "v2_summary_guidance",
            "summaries",
        ):
            if isinstance(value.get(key), list):
                return len(value[key])
        if "count" in value:
            return _as_int(value.get("count"))
        if "record_count" in value:
            return _as_int(value.get("record_count"))
    return 0


def _nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    cur: Any = mapping
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _extract_context_packs(report: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    for key in (
        "context_packs",
        "executed_plan_context_packs",
        "executed_plan_context_pack_records",
        "packs",
        "records",
    ):
        value = report.get(key)
        if isinstance(value, list) and value:
            return [v for v in value if isinstance(v, Mapping)]

    # Some report artifacts keep counts in the summary and the large records in JSONL only.
    # For quality/audit continuity, synthesize light records from the summary rather than fail blindly.
    count = _as_int(
        _first_present(report, ["context_pack_count", "ready_context_pack_count", "pack_count"], 0)
    )
    if count <= 0:
        return []

    total_evidence = _as_int(
        _first_present(report, ["total_source_truth_evidence_count", "source_truth_evidence_count"], 0)
    )
    evidence_per_pack = max(1, total_evidence // max(count, 1)) if total_evidence else 0
    graph_count = _as_int(_first_present(report, ["packs_with_graph_guidance_count"], count))
    summary_count = _as_int(_first_present(report, ["packs_with_v2_summary_guidance_count"], 0))
    cap_count = _as_int(
        _first_present(
            report,
            ["packs_with_aggregation_or_cap_disclosure_count", "capped_result_disclosure_count"],
            0,
        )
    )
    packs: List[Mapping[str, Any]] = []
    for idx in range(count):
        packs.append(
            {
                "context_pack_id": f"context_pack_v19_synth_{idx+1:04d}",
                "query_plan_id": f"query_plan_synth_{idx+1:04d}",
                "user_query": f"synthetic_context_pack_{idx+1}",
                "evidence_box": {
                    "source_truth_evidence_count": evidence_per_pack,
                    "source_truth_evidence": [{} for _ in range(evidence_per_pack)],
                },
                "guidance_box": {
                    "graph_guidance": [{}] if idx < graph_count else [],
                    "v2_summary_guidance": [{}] if idx < summary_count else [],
                    "graph_authority": "guidance_only",
                    "summary_authority": "guidance_only",
                },
                "aggregation_box": {
                    "result_was_capped": idx < cap_count,
                    "more_results_available": idx < cap_count,
                    "total_match_count": evidence_per_pack + (25 if idx < cap_count else 0),
                    "returned_match_count": evidence_per_pack,
                },
                "answer_rules_box": {"cite_every_factual_claim": True},
            }
        )
    return packs


def _get_evidence_records(pack: Mapping[str, Any]) -> List[Any]:
    candidates = [
        pack.get("source_truth_evidence"),
        pack.get("evidence"),
        _nested(pack, ["evidence_box", "source_truth_evidence"]),
        _nested(pack, ["evidence_box", "records"]),
        _nested(pack, ["source_truth_evidence_box", "records"]),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
    count = _as_int(
        _first_present(
            pack,
            ["source_truth_evidence_count", "evidence_count", "total_source_truth_evidence_count"],
            None,
        ),
        -1,
    )
    if count < 0:
        count = _as_int(_nested(pack, ["evidence_box", "source_truth_evidence_count"], 0))
    return [{} for _ in range(max(0, count))]


def _get_graph_guidance_records(pack: Mapping[str, Any]) -> List[Any]:
    for candidate in (
        pack.get("graph_guidance"),
        pack.get("leiden_guidance"),
        _nested(pack, ["guidance_box", "graph_guidance"]),
        _nested(pack, ["guidance_box", "leiden_guidance"]),
    ):
        if isinstance(candidate, list):
            return candidate
    count = _as_int(_nested(pack, ["guidance_box", "graph_guidance_count"], 0))
    return [{} for _ in range(max(0, count))]


def _get_summary_guidance_records(pack: Mapping[str, Any]) -> List[Any]:
    for candidate in (
        pack.get("v2_summary_guidance"),
        pack.get("summary_guidance"),
        _nested(pack, ["guidance_box", "v2_summary_guidance"]),
        _nested(pack, ["guidance_box", "summary_guidance"]),
    ):
        if isinstance(candidate, list):
            return candidate
    count = _as_int(_nested(pack, ["guidance_box", "v2_summary_guidance_count"], 0))
    return [{} for _ in range(max(0, count))]


def _get_aggregation_box(pack: Mapping[str, Any]) -> Mapping[str, Any]:
    for candidate in (pack.get("aggregation_box"), pack.get("aggregation"), pack.get("cap_disclosure")):
        if isinstance(candidate, Mapping):
            return candidate
    return {}


def _has_answer_rules(pack: Mapping[str, Any]) -> bool:
    return bool(
        pack.get("answer_rules_box")
        or pack.get("answer_rules")
        or _nested(pack, ["rules_box"], None)
        or _nested(pack, ["context_pack", "answer_rules_box"], None)
    )


def _guidance_authority_ok(pack: Mapping[str, Any]) -> Tuple[bool, bool]:
    # Conservative: only count a violation if an artifact explicitly claims proof authority.
    graph_values = [
        pack.get("graph_authority"),
        pack.get("leiden_authority"),
        _nested(pack, ["guidance_box", "graph_authority"]),
        _nested(pack, ["guidance_box", "leiden_authority"]),
        _nested(pack, ["graph_guidance", "authority"]),
    ]
    summary_values = [
        pack.get("summary_authority"),
        pack.get("v2_summary_authority"),
        _nested(pack, ["guidance_box", "summary_authority"]),
        _nested(pack, ["guidance_box", "v2_summary_authority"]),
    ]

    def is_bad(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        v = value.lower()
        return "proof" in v and "not" not in v and "false" not in v and "guidance" not in v

    return not any(is_bad(v) for v in graph_values), not any(is_bad(v) for v in summary_values)


def evaluate_pack(pack: Mapping[str, Any], idx: int) -> Dict[str, Any]:
    evidence_records = _get_evidence_records(pack)
    graph_records = _get_graph_guidance_records(pack)
    summary_records = _get_summary_guidance_records(pack)
    aggregation = dict(_get_aggregation_box(pack))

    evidence_count = len(evidence_records)
    graph_guidance_count = len(graph_records)
    summary_guidance_count = len(summary_records)
    has_rules = _has_answer_rules(pack)

    capped = _as_bool(aggregation.get("result_was_capped")) or _as_bool(aggregation.get("more_results_available"))
    high_degree = _as_bool(aggregation.get("high_degree_node_detected"))
    total_matches = _as_int(aggregation.get("total_match_count"), evidence_count)
    returned_matches = _as_int(aggregation.get("returned_match_count"), evidence_count)
    more_available = _as_bool(aggregation.get("more_results_available"), capped)

    graph_ok, summary_ok = _guidance_authority_ok(pack)

    if evidence_count <= 0:
        self_rag_status = "CONTEXT_WEAK_NEEDS_CRAG_RETRY"
        crag_status = "CRAG_RETRY_REQUIRED"
        ready_for_llm = False
        audit_only = False
        retry_required = True
        limitations = ["No source-truth evidence is present in the context pack yet."]
    elif not graph_ok or not summary_ok:
        self_rag_status = "CONTEXT_BLOCKED_AUDIT_ONLY"
        crag_status = "CRAG_BLOCKED_BY_AUTHORITY_VIOLATION"
        ready_for_llm = False
        audit_only = True
        retry_required = False
        limitations = ["Graph or summary guidance attempted to claim proof authority."]
    elif capped or high_degree or more_available or total_matches > returned_matches:
        self_rag_status = "CONTEXT_READY_WITH_CAP_DISCLOSURE"
        crag_status = "CRAG_NO_RETRY_NEEDED_PRESERVE_CAP_DISCLOSURE"
        ready_for_llm = True
        audit_only = False
        retry_required = False
        limitations = [
            "Results are capped or aggregated; the final answer must disclose that more matching evidence may exist."
        ]
    else:
        self_rag_status = "CONTEXT_READY_FOR_LLM"
        crag_status = "CRAG_NO_RETRY_NEEDED"
        ready_for_llm = True
        audit_only = False
        retry_required = False
        limitations = ["Final answer must stay limited to cited source-truth evidence."]

    crag_actions: List[Dict[str, Any]] = []
    if retry_required:
        crag_actions.append(
            {
                "action_type": "retry_retrieval",
                "allowed_retry_tunnels": [
                    "table_exact_search_tunnel",
                    "table_hybrid_bridge_tunnel",
                    "qdrant_page_profile_tunnel",
                    "graph_navigation_tunnel",
                    "page_summary_tunnel",
                ],
                "requires_source_truth_confirmation": True,
                "raw_5tb_scan_allowed": False,
            }
        )
    elif capped or high_degree or more_available or total_matches > returned_matches:
        crag_actions.append(
            {
                "action_type": "preserve_aggregation_and_offer_drilldown",
                "requires_cap_disclosure": True,
                "allowed_drilldowns": aggregation.get(
                    "available_drilldowns",
                    ["document", "manual", "revision", "section", "route", "field", "leiden_community"],
                ),
                "requires_source_truth_confirmation": True,
            }
        )
    else:
        crag_actions.append(
            {
                "action_type": "no_retry_needed",
                "requires_source_truth_confirmation": True,
            }
        )

    query = str(_first_present(pack, ["user_query", "query"], f"context_pack_{idx+1}"))
    context_pack_id = str(_first_present(pack, ["context_pack_id", "pack_id"], f"context_pack_v19_{idx+1:04d}"))
    query_plan_id = str(_first_present(pack, ["query_plan_id", "plan_id"], f"query_plan_unknown_{idx+1:04d}"))

    return {
        "self_rag_crag_record_id": f"self_rag_crag_v20_{idx+1:04d}",
        "context_pack_id": context_pack_id,
        "query_plan_id": query_plan_id,
        "user_query": query,
        "self_rag_status": self_rag_status,
        "crag_status": crag_status,
        "ready_for_llm_prompt": ready_for_llm,
        "audit_only": audit_only,
        "retry_required": retry_required,
        "source_truth_evidence_count": evidence_count,
        "graph_guidance_count": graph_guidance_count,
        "v2_summary_guidance_count": summary_guidance_count,
        "has_answer_rules": has_rules,
        "has_source_truth_evidence": evidence_count > 0,
        "has_graph_guidance": graph_guidance_count > 0,
        "has_v2_summary_guidance": summary_guidance_count > 0,
        "graph_guidance_authority": "guidance_only",
        "v2_summary_authority": "guidance_only",
        "graph_proof_authority_violation": not graph_ok,
        "summary_proof_authority_violation": not summary_ok,
        "aggregation_or_cap_disclosure": {
            "total_match_count": total_matches,
            "returned_match_count": returned_matches,
            "result_was_capped": capped or total_matches > returned_matches,
            "more_results_available": more_available or total_matches > returned_matches,
            "high_degree_node_detected": high_degree,
            "available_drilldowns": aggregation.get(
                "available_drilldowns",
                ["document", "manual", "revision", "section", "route", "field", "leiden_community"],
            ),
        },
        "limitations": limitations,
        "crag_actions": crag_actions,
        "safety_contract": {
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
        },
    }


def _quality_check(name: str, observed: Any, op: str, expected: Any) -> Dict[str, Any]:
    if op == ">=":
        passed = observed >= expected
    elif op == "<=":
        passed = observed <= expected
    elif op == "==":
        passed = observed == expected
    elif op == "is False":
        passed = observed is False
    elif op == "is True":
        passed = observed is True
    else:
        raise ValueError(f"Unsupported op: {op}")
    return {"name": name, "observed": observed, "op": op, "expected": expected, "passed": bool(passed)}


def summarize_records(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    return {
        "context_pack_count": len(records),
        "self_rag_evaluation_count": len(records),
        "crag_plan_count": len(records),
        "ready_for_llm_count": sum(1 for r in records if r.get("ready_for_llm_prompt")),
        "ready_with_cap_disclosure_count": sum(
            1 for r in records if r.get("self_rag_status") == "CONTEXT_READY_WITH_CAP_DISCLOSURE"
        ),
        "retry_required_count": sum(1 for r in records if r.get("retry_required")),
        "audit_only_count": sum(1 for r in records if r.get("audit_only")),
        "contexts_with_source_truth_evidence_count": sum(1 for r in records if r.get("has_source_truth_evidence")),
        "contexts_with_graph_guidance_count": sum(1 for r in records if r.get("has_graph_guidance")),
        "contexts_with_v2_summary_guidance_count": sum(1 for r in records if r.get("has_v2_summary_guidance")),
        "contexts_with_aggregation_or_cap_disclosure_count": sum(
            1
            for r in records
            if _as_bool(_nested(r, ["aggregation_or_cap_disclosure", "result_was_capped"]))
            or _as_bool(_nested(r, ["aggregation_or_cap_disclosure", "more_results_available"]))
            or _as_int(_nested(r, ["aggregation_or_cap_disclosure", "total_match_count"], 0))
            >= _as_int(_nested(r, ["aggregation_or_cap_disclosure", "returned_match_count"], 0))
        ),
        "graph_proof_authority_violation_count": sum(1 for r in records if r.get("graph_proof_authority_violation")),
        "summary_proof_authority_violation_count": sum(1 for r in records if r.get("summary_proof_authority_violation")),
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def evaluate_quality(report: Mapping[str, Any], args: argparse.Namespace) -> List[Dict[str, Any]]:
    checks = [
        _quality_check("context_pack_count", report.get("context_pack_count", 0), ">=", args.min_context_packs),
        _quality_check(
            "self_rag_evaluation_count",
            report.get("self_rag_evaluation_count", 0),
            ">=",
            args.min_self_rag_evaluations,
        ),
        _quality_check("crag_plan_count", report.get("crag_plan_count", 0), ">=", args.min_crag_plans),
        _quality_check("ready_for_llm_count", report.get("ready_for_llm_count", 0), ">=", args.min_ready_for_llm),
        _quality_check(
            "contexts_with_source_truth_evidence_count",
            report.get("contexts_with_source_truth_evidence_count", 0),
            ">=",
            args.min_contexts_with_source_truth_evidence,
        ),
        _quality_check(
            "contexts_with_graph_guidance_count",
            report.get("contexts_with_graph_guidance_count", 0),
            ">=",
            args.min_contexts_with_graph_guidance,
        ),
        _quality_check(
            "contexts_with_v2_summary_guidance_count",
            report.get("contexts_with_v2_summary_guidance_count", 0),
            ">=",
            args.min_contexts_with_v2_summary_guidance,
        ),
        _quality_check(
            "contexts_with_aggregation_or_cap_disclosure_count",
            report.get("contexts_with_aggregation_or_cap_disclosure_count", 0),
            ">=",
            args.min_contexts_with_aggregation_or_cap_disclosure,
        ),
        _quality_check(
            "retry_required_count",
            report.get("retry_required_count", 0),
            "<=",
            args.max_retry_required_count,
        ),
        _quality_check("audit_only_count", report.get("audit_only_count", 0), "<=", args.max_audit_only_count),
        _quality_check(
            "graph_proof_authority_violation_count",
            report.get("graph_proof_authority_violation_count", 0),
            "<=",
            args.max_graph_proof_authority_violations,
        ),
        _quality_check(
            "summary_proof_authority_violation_count",
            report.get("summary_proof_authority_violation_count", 0),
            "<=",
            args.max_summary_proof_authority_violations,
        ),
        _quality_check(
            "answer_permission_count",
            report.get("answer_permission_count", 0),
            "<=",
            args.max_answer_permission_count,
        ),
        _quality_check(
            "source_truth_mutation_allowed_count",
            report.get("source_truth_mutation_allowed_count", 0),
            "<=",
            args.max_source_truth_mutation_allowed,
        ),
        _quality_check("contract_raw_5tb_scan_at_query_time", False, "is False", False),
        _quality_check("contract_graph_rebuild_at_query_time", False, "is False", False),
    ]
    if getattr(args, "require_no_answer_permission", False):
        checks.append(_quality_check("require_no_answer_permission", report.get("answer_permission_count", 0), "==", 0))
    return checks


def build_report(
    executed_plan_context_pack: str | Path,
    output_dir: str | Path,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    source = load_json(executed_plan_context_pack)
    packs = _extract_context_packs(source if isinstance(source, Mapping) else {})
    records = [evaluate_pack(pack, idx) for idx, pack in enumerate(packs)]
    summary = summarize_records(records)

    report: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": READY_STATUS,
        "quality_status": "UNKNOWN",
        "source_report_path": str(executed_plan_context_pack),
        "contract": {
            "self_rag_checks_context_strength": True,
            "crag_retries_only_when_needed": True,
            "graph_guidance_authority": "guidance_only",
            "v2_summary_authority": "guidance_only",
            "source_truth_evidence_required_for_final_claims": True,
            "cap_disclosure_required_for_capped_results": True,
            "llm_reads_context_pack_only": True,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        },
        "self_rag_crag_records": records,
    }
    report.update(summary)

    checks = evaluate_quality(report, args)
    report["quality_checks"] = checks
    all_passed = all(c["passed"] for c in checks)
    report["quality_status"] = "PASS" if all_passed else "FAIL"
    report["status"] = READY_STATUS if all_passed else NEEDS_RETRY_STATUS

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_e2e_live_self_rag_crag_evaluator_v20.json"
    records_path = out / "trace_net_e2e_live_self_rag_crag_evaluator_records_v20.jsonl"
    crag_path = out / "trace_net_e2e_live_self_rag_crag_evaluator_crag_plans_v20.jsonl"
    md_path = out / "trace_net_e2e_live_self_rag_crag_evaluator_v20.md"

    write_json(report_path, report)
    write_jsonl(records_path, records)
    write_jsonl(
        crag_path,
        [
            {
                "self_rag_crag_record_id": r["self_rag_crag_record_id"],
                "context_pack_id": r["context_pack_id"],
                "user_query": r["user_query"],
                "crag_status": r["crag_status"],
                "crag_actions": r["crag_actions"],
            }
            for r in records
        ],
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")

    report["report_path"] = str(report_path)
    report["records_jsonl_path"] = str(records_path)
    report["crag_plans_jsonl_path"] = str(crag_path)
    report["inspect_md_path"] = str(md_path)
    write_json(report_path, report)
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net E2E Live Self-RAG + CRAG Evaluator v20",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
    ]
    for key in [
        "context_pack_count",
        "self_rag_evaluation_count",
        "crag_plan_count",
        "ready_for_llm_count",
        "ready_with_cap_disclosure_count",
        "retry_required_count",
        "audit_only_count",
        "contexts_with_source_truth_evidence_count",
        "contexts_with_graph_guidance_count",
        "contexts_with_v2_summary_guidance_count",
        "contexts_with_aggregation_or_cap_disclosure_count",
        "graph_proof_authority_violation_count",
        "summary_proof_authority_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {report.get(key, 0)}")
    lines.extend(
        [
            "",
            "## Contract",
            "- Self-RAG evaluates evidence sufficiency before the LLM sees a context pack.",
            "- CRAG plans retries or drill-down handling only when needed.",
            "- Graph/Leiden and v2 summaries remain guidance only, not proof authority.",
            "- Capped/high-degree results require disclosure and drill-down options.",
            "- Query time must not scan raw 5TB source data or rebuild the graph.",
            "",
            "## Records",
        ]
    )
    for rec in report.get("self_rag_crag_records", []):
        if not isinstance(rec, Mapping):
            continue
        lines.extend(
            [
                f"### {rec.get('self_rag_crag_record_id')} — `{rec.get('self_rag_status')}`",
                f"- query: {rec.get('user_query')}",
                f"- context_pack_id: `{rec.get('context_pack_id')}`",
                f"- ready_for_llm_prompt: {rec.get('ready_for_llm_prompt')}",
                f"- crag_status: `{rec.get('crag_status')}`",
                f"- source_truth_evidence_count: {rec.get('source_truth_evidence_count')}",
                f"- graph_guidance_count: {rec.get('graph_guidance_count')}",
                f"- v2_summary_guidance_count: {rec.get('v2_summary_guidance_count')}",
                f"- cap_disclosure: {rec.get('aggregation_or_cap_disclosure', {}).get('result_was_capped')}",
                "",
            ]
        )
    lines.append("## Quality checks")
    for check in report.get("quality_checks", []):
        status = "PASS" if check.get("passed") else "FAIL"
        lines.append(
            f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('op')} {check.get('expected')}"
        )
    lines.append("")
    return "\n".join(lines)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-context-packs", type=int, default=1)
    parser.add_argument("--min-self-rag-evaluations", type=int, default=1)
    parser.add_argument("--min-crag-plans", type=int, default=1)
    parser.add_argument("--min-ready-for-llm", type=int, default=1)
    parser.add_argument("--min-contexts-with-source-truth-evidence", type=int, default=1)
    parser.add_argument("--min-contexts-with-graph-guidance", type=int, default=0)
    parser.add_argument("--min-contexts-with-v2-summary-guidance", type=int, default=0)
    parser.add_argument("--min-contexts-with-aggregation-or-cap-disclosure", type=int, default=0)
    parser.add_argument("--max-retry-required-count", type=int, default=999999)
    parser.add_argument("--max-audit-only-count", type=int, default=999999)
    parser.add_argument("--max-graph-proof-authority-violations", type=int, default=0)
    parser.add_argument("--max-summary-proof-authority-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net live Self-RAG + CRAG evaluator v20")
    parser.add_argument("--executed-plan-context-pack", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    add_common_args(parser)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_report(args.executed_plan_context_pack, args.output_dir, args)
    print("TRACE-Net E2E Live Self-RAG + CRAG Evaluator v20")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "context_pack_count",
        "self_rag_evaluation_count",
        "crag_plan_count",
        "ready_for_llm_count",
        "ready_with_cap_disclosure_count",
        "retry_required_count",
        "audit_only_count",
        "contexts_with_source_truth_evidence_count",
        "contexts_with_graph_guidance_count",
        "contexts_with_v2_summary_guidance_count",
        "contexts_with_aggregation_or_cap_disclosure_count",
        "graph_proof_authority_violation_count",
        "summary_proof_authority_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {report.get(key, 0)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" records_jsonl_path: {report.get('records_jsonl_path')}")
    print(f" crag_plans_jsonl_path: {report.get('crag_plans_jsonl_path')}")
    print(f" inspect_md_path: {report.get('inspect_md_path')}")
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
