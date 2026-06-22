"""TRACE-Net E2E Context Pack Builder v1.

Turns local ranked retrieval groups into retrieval-only context packs.

The module intentionally does not answer questions, prove claims, mutate source truth,
or write to Postgres/Qdrant/OpenSearch. It is the bridge between retrieval runtime
and later sufficiency/final-gate modules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"
STATUS_BUILT = "E2E_CONTEXT_PACK_BUILT"
READY_STATUS = "E2E_CONTEXT_PACK_READY_FOR_FINAL_GATE"

REPORT_NAME = "trace_net_e2e_context_pack_builder_v1.json"
QUALITY_NAME = "trace_net_e2e_context_pack_builder_v1_quality.json"
CONTEXT_PACKS_JSONL_NAME = "trace_net_e2e_context_packs_v1.jsonl"
CONTEXT_ITEMS_JSONL_NAME = "trace_net_e2e_context_items_v1.jsonl"
INSPECT_MD_NAME = "trace_net_e2e_context_pack_builder_v1_inspect.md"

REQUIRED_HIT_KEYS = ("page_id", "field_name", "normalized_value")


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(_safe_str(p) for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _runtime_quality_pass(runtime: Mapping[str, Any]) -> bool:
    if _safe_str(runtime.get("quality_status")).upper() == QUALITY_PASS:
        return True
    summary = runtime.get("summary") or {}
    if isinstance(summary, Mapping):
        return _as_bool(summary.get("source_query_input_quality_pass")) and _as_bool(summary.get("source_bridge_quality_pass"))
    return False


def _runtime_ready(runtime: Mapping[str, Any]) -> bool:
    contract = runtime.get("runtime_contract") or {}
    summary = runtime.get("summary") or {}
    if isinstance(contract, Mapping) and _as_bool(contract.get("ready_for_context_pack")):
        return True
    if isinstance(summary, Mapping) and _as_bool(summary.get("ready_for_context_pack")):
        return True
    status = _safe_str(summary.get("e2e_hybrid_retrieval_runtime_status") if isinstance(summary, Mapping) else "")
    return status == "E2E_HYBRID_RETRIEVAL_RUNTIME_READY_FOR_CONTEXT_PACK"


def _get_retrieval_groups(runtime: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    groups = runtime.get("retrieval_groups")
    if isinstance(groups, list):
        return [g for g in groups if isinstance(g, Mapping)]
    # defensive fallback for future artifact naming
    groups = runtime.get("hybrid_retrieval_groups")
    if isinstance(groups, list):
        return [g for g in groups if isinstance(g, Mapping)]
    return []


def _get_hits(group: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    hits = group.get("hits")
    if isinstance(hits, list):
        return [h for h in hits if isinstance(h, Mapping)]
    hits = group.get("retrieval_hits")
    if isinstance(hits, list):
        return [h for h in hits if isinstance(h, Mapping)]
    return []


def _has_required_hit_keys(hit: Mapping[str, Any]) -> bool:
    return all(_safe_str(hit.get(k)) for k in REQUIRED_HIT_KEYS)


def build_context_item(query_id: str, query_index: int, hit_index: int, hit: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = _safe_str(hit.get("page_id"))
    field_name = _safe_str(hit.get("field_name"))
    normalized_value = _safe_str(hit.get("normalized_value") or hit.get("value") or hit.get("text"))
    table_id = _safe_str(hit.get("table_id") or hit.get("source_table_id") or "")
    route = _safe_str(hit.get("route") or hit.get("source_route") or "table")
    retrieval_channel = _safe_str(hit.get("retrieval_channel") or hit.get("channel") or "table_hybrid_retrieval_bridge")
    score = _num(hit.get("retrieval_score", hit.get("score")), 0.0)
    boost = _num(hit.get("routing_boost"), 1.0)
    item_id = _stable_id("e2e_context_item_v1", query_id, page_id, field_name, normalized_value, hit_index)
    citation_anchor = f"{page_id}#{field_name}:{normalized_value}" if page_id and field_name and normalized_value else page_id
    item = {
        "context_item_id": item_id,
        "query_id": query_id,
        "query_rank": query_index,
        "hit_rank": hit_index + 1,
        "page_id": page_id,
        "table_id": table_id,
        "route": route,
        "field_name": field_name,
        "normalized_value": normalized_value,
        "evidence_text": f"{field_name}: {normalized_value}" if field_name and normalized_value else normalized_value,
        "evidence_type": "table_route_value",
        "retrieval_channel": retrieval_channel,
        "retrieval_score": score,
        "routing_boost": boost,
        "citation_anchor": citation_anchor,
        "source_trace": {
            "page_id": page_id,
            "route": route,
            "field_name": field_name,
            "normalized_value": normalized_value,
            "source_artifact": "trace_net_e2e_hybrid_retrieval_runtime_v1",
        },
        "citation_ready": bool(page_id and field_name and normalized_value),
        "source_trace_ready": bool(page_id),
        "retrieval_only": True,
        "ranking_signal_available": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "unsafe": False,
        "schema_complete": _has_required_hit_keys({**hit, "normalized_value": normalized_value}),
    }
    # carry through selected provenance if present, but never authority.
    for optional_key in ("source_document_id", "source_package_id", "source_page_number", "ocr_page_number"):
        if optional_key in hit:
            item[optional_key] = hit[optional_key]
    return item


def build_context_pack(group: Mapping[str, Any], query_index: int, *, top_k: int) -> Dict[str, Any]:
    query_id = _safe_str(group.get("query_id") or f"e2e_query_unknown_{query_index:04d}")
    hits = _get_hits(group)[: max(0, top_k)]
    items = [build_context_item(query_id, query_index, idx, hit) for idx, hit in enumerate(hits)]
    page_ids = sorted({item["page_id"] for item in items if item.get("page_id")})
    field_names = sorted({item["field_name"] for item in items if item.get("field_name")})
    pack_id = _stable_id("e2e_context_pack_v1", query_id, group.get("user_query"), len(items))
    pack = {
        "context_pack_id": pack_id,
        "query_id": query_id,
        "query_intent": _safe_str(group.get("query_intent")),
        "user_query": _safe_str(group.get("user_query")),
        "retrieval_status": _safe_str(group.get("retrieval_status") or "UNKNOWN"),
        "context_pack_status": "CONTEXT_PACK_READY" if items else "CONTEXT_PACK_EMPTY",
        "context_item_count": len(items),
        "page_ids": page_ids,
        "field_names": field_names,
        "top_context_items": items,
        "context_pack_contract": {
            "retrieval_permission": "ranking_only_until_final_gate",
            "answer_authority": "blocked",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "requires_final_gate": True,
        },
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "unsafe": False,
    }
    return pack


def _count_bad(records: Iterable[Mapping[str, Any]], key: str) -> int:
    return sum(1 for rec in records if _as_bool(rec.get(key)))


def _quality_check(name: str, observed: Any, expected: str, passed: bool) -> Dict[str, Any]:
    return {
        "name": name,
        "observed": observed,
        "expected": expected,
        "passed": bool(passed),
    }


def evaluate_quality(report: Mapping[str, Any], args: argparse.Namespace) -> Tuple[str, List[Dict[str, Any]]]:
    summary = report.get("summary") or {}
    if not isinstance(summary, Mapping):
        summary = {}
    checks: List[Dict[str, Any]] = []
    add = checks.append
    add(_quality_check("source_runtime_quality_pass", summary.get("source_runtime_quality_pass"), "is True", _as_bool(summary.get("source_runtime_quality_pass"))))
    add(_quality_check("source_runtime_ready_for_context_pack", summary.get("source_runtime_ready_for_context_pack"), "is True", _as_bool(summary.get("source_runtime_ready_for_context_pack"))))
    add(_quality_check("source_retrieval_group_count", summary.get("source_retrieval_group_count", 0), f">= {args.min_source_retrieval_groups}", int(summary.get("source_retrieval_group_count", 0)) >= args.min_source_retrieval_groups))
    add(_quality_check("context_pack_count", summary.get("context_pack_count", 0), f">= {args.min_context_packs}", int(summary.get("context_pack_count", 0)) >= args.min_context_packs))
    add(_quality_check("context_pack_with_items_count", summary.get("context_pack_with_items_count", 0), f">= {args.min_context_packs_with_items}", int(summary.get("context_pack_with_items_count", 0)) >= args.min_context_packs_with_items))
    add(_quality_check("total_context_item_count", summary.get("total_context_item_count", 0), f">= {args.min_total_context_items}", int(summary.get("total_context_item_count", 0)) >= args.min_total_context_items))
    add(_quality_check("page_with_context_item_count", summary.get("page_with_context_item_count", 0), f">= {args.min_pages_with_context_items}", int(summary.get("page_with_context_item_count", 0)) >= args.min_pages_with_context_items))
    add(_quality_check("citation_ready_context_item_count", summary.get("citation_ready_context_item_count", 0), f">= {args.min_citation_ready_items}", int(summary.get("citation_ready_context_item_count", 0)) >= args.min_citation_ready_items))
    add(_quality_check("source_trace_ready_context_item_count", summary.get("source_trace_ready_context_item_count", 0), f">= {args.min_source_trace_ready_items}", int(summary.get("source_trace_ready_context_item_count", 0)) >= args.min_source_trace_ready_items))
    add(_quality_check("field_count", summary.get("field_count", 0), f">= {args.min_field_count}", int(summary.get("field_count", 0)) >= args.min_field_count))
    add(_quality_check("schema_missing_required_key_item_count", summary.get("schema_missing_required_key_item_count", 0), "== 0", int(summary.get("schema_missing_required_key_item_count", 0)) == 0))
    add(_quality_check("unsafe_context_record_count", summary.get("unsafe_context_record_count", 0), f"<= {args.max_unsafe_records}", int(summary.get("unsafe_context_record_count", 0)) <= args.max_unsafe_records))
    add(_quality_check("answer_permission_count", summary.get("answer_permission_count", 0), f"<= {args.max_answer_permission_count}", int(summary.get("answer_permission_count", 0)) <= args.max_answer_permission_count))
    add(_quality_check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), f"<= {args.max_source_truth_mutation_allowed}", int(summary.get("source_truth_mutation_allowed_count", 0)) <= args.max_source_truth_mutation_allowed))
    add(_quality_check("can_answer_directly_count", summary.get("can_answer_directly_count", 0), "== 0", int(summary.get("can_answer_directly_count", 0)) == 0))
    add(_quality_check("can_prove_claims_count", summary.get("can_prove_claims_count", 0), "== 0", int(summary.get("can_prove_claims_count", 0)) == 0))
    add(_quality_check("postgres_write_attempt_count", summary.get("postgres_write_attempt_count", 0), "== 0", int(summary.get("postgres_write_attempt_count", 0)) == 0))
    add(_quality_check("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count", 0), "== 0", int(summary.get("qdrant_write_attempt_count", 0)) == 0))
    add(_quality_check("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count", 0), "== 0", int(summary.get("opensearch_write_attempt_count", 0)) == 0))
    add(_quality_check("opensearch_upload_attempt_count", summary.get("opensearch_upload_attempt_count", 0), "== 0", int(summary.get("opensearch_upload_attempt_count", 0)) == 0))
    if args.require_source_runtime_quality_pass:
        # already included above; keep as explicit gate
        pass
    if args.require_no_answer_permission:
        add(_quality_check("all_context_retrieval_only", summary.get("all_context_retrieval_only", False), "is True", _as_bool(summary.get("all_context_retrieval_only"))))
    status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    return status, checks


def build_report(runtime_path: Path, output_dir: Path, *, top_k: int, args: argparse.Namespace) -> Dict[str, Any]:
    runtime = _read_json(runtime_path)
    retrieval_groups = _get_retrieval_groups(runtime)
    context_packs = [build_context_pack(group, idx + 1, top_k=top_k) for idx, group in enumerate(retrieval_groups)]
    context_items: List[Dict[str, Any]] = []
    for pack in context_packs:
        for item in pack.get("top_context_items", []):
            if isinstance(item, dict):
                context_items.append(item)

    field_counts: Dict[str, int] = {}
    for item in context_items:
        field = _safe_str(item.get("field_name"))
        if field:
            field_counts[field] = field_counts.get(field, 0) + 1

    page_ids = {item.get("page_id") for item in context_items if _safe_str(item.get("page_id"))}
    summary: Dict[str, Any] = {
        "source_runtime_path": str(runtime_path),
        "source_runtime_quality_pass": _runtime_quality_pass(runtime),
        "source_runtime_ready_for_context_pack": _runtime_ready(runtime),
        "source_retrieval_group_count": len(retrieval_groups),
        "source_total_retrieval_hit_count": (runtime.get("summary") or {}).get("total_retrieval_hit_count", 0) if isinstance(runtime.get("summary"), Mapping) else 0,
        "context_pack_count": len(context_packs),
        "context_pack_with_items_count": sum(1 for p in context_packs if int(p.get("context_item_count", 0)) > 0),
        "total_context_item_count": len(context_items),
        "page_with_context_item_count": len(page_ids),
        "field_count": len(field_counts),
        "field_counts": dict(sorted(field_counts.items())),
        "citation_ready_context_item_count": sum(1 for item in context_items if _as_bool(item.get("citation_ready"))),
        "source_trace_ready_context_item_count": sum(1 for item in context_items if _as_bool(item.get("source_trace_ready"))),
        "schema_missing_required_key_item_count": sum(1 for item in context_items if not _as_bool(item.get("schema_complete"))),
        "unsafe_context_record_count": _count_bad(context_packs, "unsafe") + _count_bad(context_items, "unsafe"),
        "answer_permission_count": _count_bad(context_packs, "answer_permission") + _count_bad(context_items, "answer_permission"),
        "can_answer_directly_count": _count_bad(context_packs, "can_answer_directly") + _count_bad(context_items, "can_answer_directly"),
        "can_prove_claims_count": _count_bad(context_packs, "can_prove_claims") + _count_bad(context_items, "can_prove_claims"),
        "source_truth_mutation_allowed_count": _count_bad(context_packs, "source_truth_mutation_allowed") + _count_bad(context_items, "source_truth_mutation_allowed"),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "ready_for_final_gate": True,
        "all_context_retrieval_only": all(_as_bool(item.get("retrieval_only")) for item in context_items) if context_items else False,
        "retrieval_permission": "ranking_only_until_final_gate",
        "answer_authority": "blocked",
    }
    report: Dict[str, Any] = {
        "artifact_name": "trace_net_e2e_context_pack_builder_v1",
        "status": STATUS_BUILT,
        "quality_status": QUALITY_FAIL,
        "e2e_context_pack_status": READY_STATUS,
        "context_pack_contract": {
            "purpose": "Turn ranked retrieval groups into citation/source-trace-ready context packs for final gate review.",
            "retrieval_permission": "ranking_only_until_final_gate",
            "answer_authority": "blocked",
            "ready_for_final_gate": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
        },
        "summary": summary,
        "context_packs": context_packs,
        "context_items": context_items,
        "quality_checks": [],
        "paths": {
            "report_path": str(output_dir / REPORT_NAME),
            "quality_path": str(output_dir / QUALITY_NAME),
            "context_packs_jsonl_path": str(output_dir / CONTEXT_PACKS_JSONL_NAME),
            "context_items_jsonl_path": str(output_dir / CONTEXT_ITEMS_JSONL_NAME),
            "inspect_md_path": str(output_dir / INSPECT_MD_NAME),
        },
    }
    quality_status, checks = evaluate_quality(report, args)
    report["quality_status"] = quality_status
    report["quality_checks"] = checks
    return report


def write_inspect_md(path: Path, report: Mapping[str, Any]) -> None:
    summary = report.get("summary") or {}
    contract = report.get("context_pack_contract") or {}
    packs = report.get("context_packs") or []
    lines: List[str] = []
    lines.append("# TRACE-Net E2E Context Pack Builder v1 Inspect")
    lines.append("")
    lines.append(f"Quality status: **{report.get('quality_status', QUALITY_FAIL)}**")
    lines.append("")
    lines.append("## Purpose")
    lines.append("This artifact converts ranked retrieval groups into context packs for the later final gate.")
    lines.append("It is intentionally retrieval-only: context can be reviewed, cited, and ranked, but cannot answer directly.")
    lines.append("")
    lines.append("## Context pack contract")
    for key in ("retrieval_permission", "answer_authority", "ready_for_final_gate", "can_answer_directly", "can_prove_claims", "source_truth_mutation_allowed", "writes_to_postgres", "writes_to_qdrant", "writes_to_opensearch", "uploads_to_opensearch"):
        lines.append(f"- {key}: {contract.get(key)}")
    lines.append("")
    lines.append("## Main counters")
    for key in ("source_retrieval_group_count", "context_pack_count", "context_pack_with_items_count", "total_context_item_count", "page_with_context_item_count", "field_count", "citation_ready_context_item_count", "source_trace_ready_context_item_count", "schema_missing_required_key_item_count"):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    lines.append("## Field counts")
    field_counts = summary.get("field_counts") if isinstance(summary, Mapping) else {}
    if isinstance(field_counts, Mapping) and field_counts:
        for key, value in field_counts.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Safety/write counters")
    for key in ("unsafe_context_record_count", "answer_permission_count", "can_answer_directly_count", "can_prove_claims_count", "source_truth_mutation_allowed_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count", "opensearch_upload_attempt_count"):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    lines.append("## Context packs")
    if isinstance(packs, list):
        for pack in packs:
            if not isinstance(pack, Mapping):
                continue
            lines.append(f"- {pack.get('query_id')} | {pack.get('query_intent')} | query='{pack.get('user_query')}' | items={pack.get('context_item_count')}")
            items = pack.get("top_context_items") or []
            if isinstance(items, list):
                for item in items[:5]:
                    if isinstance(item, Mapping):
                        lines.append(f"  - {item.get('page_id')} | {item.get('field_name')} | {item.get('normalized_value')} | citation_ready={item.get('citation_ready')} | source_trace_ready={item.get('source_trace_ready')}")
    lines.append("")
    lines.append("## Quality checks")
    checks = report.get("quality_checks") or []
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, Mapping):
                status = "PASS" if check.get("passed") else "FAIL"
                lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(report: Mapping[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, report)
    _write_json(output_dir / QUALITY_NAME, {"quality_status": report.get("quality_status"), "quality_checks": report.get("quality_checks", []), "summary": report.get("summary", {})})
    packs = report.get("context_packs") if isinstance(report.get("context_packs"), list) else []
    items = report.get("context_items") if isinstance(report.get("context_items"), list) else []
    _write_jsonl(output_dir / CONTEXT_PACKS_JSONL_NAME, [p for p in packs if isinstance(p, Mapping)])
    _write_jsonl(output_dir / CONTEXT_ITEMS_JSONL_NAME, [i for i in items if isinstance(i, Mapping)])
    write_inspect_md(output_dir / INSPECT_MD_NAME, report)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E context packs from retrieval runtime output.")
    parser.add_argument("--e2e-hybrid-retrieval-runtime", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-source-retrieval-groups", type=int, default=5)
    parser.add_argument("--min-context-packs", type=int, default=5)
    parser.add_argument("--min-context-packs-with-items", type=int, default=4)
    parser.add_argument("--min-total-context-items", type=int, default=10)
    parser.add_argument("--min-pages-with-context-items", type=int, default=2)
    parser.add_argument("--min-citation-ready-items", type=int, default=10)
    parser.add_argument("--min-source-trace-ready-items", type=int, default=10)
    parser.add_argument("--min-field-count", type=int, default=3)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-runtime-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_report(args.e2e_hybrid_retrieval_runtime, args.output_dir, top_k=args.top_k, args=args)
    write_outputs(report, args.output_dir)
    summary = report["summary"]
    print("TRACE-Net E2E Context Pack Builder v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    print(f" e2e_context_pack_status: {report['e2e_context_pack_status']}")
    for key in (
        "source_retrieval_group_count",
        "context_pack_count",
        "context_pack_with_items_count",
        "total_context_item_count",
        "page_with_context_item_count",
        "field_count",
        "citation_ready_context_item_count",
        "source_trace_ready_context_item_count",
        "schema_missing_required_key_item_count",
        "unsafe_context_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {args.output_dir / REPORT_NAME}")
    print(f" context_packs_jsonl_path: {args.output_dir / CONTEXT_PACKS_JSONL_NAME}")
    print(f" context_items_jsonl_path: {args.output_dir / CONTEXT_ITEMS_JSONL_NAME}")
    print(f" inspect_md_path: {args.output_dir / INSPECT_MD_NAME}")
    if args.quality and report["quality_status"] != QUALITY_PASS:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
