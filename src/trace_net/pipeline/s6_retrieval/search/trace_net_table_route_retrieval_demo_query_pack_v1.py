"""TRACE-Net table-route retrieval demo query pack v1.

This local-only module turns the already-passing table route retrieval readiness
artifacts into a human-readable demo pack.  The demo pack is meant to show how a
plain user query can match table-route values and influence retrieval ranking,
while staying blocked from final-answer authority.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

STATUS_BUILT = "TABLE_ROUTE_RETRIEVAL_DEMO_QUERY_PACK_BUILT"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

REPORT_NAME = "trace_net_table_route_retrieval_demo_query_pack_v1.json"
QUALITY_NAME = "trace_net_table_route_retrieval_demo_query_pack_v1_quality.json"
DEMO_JSONL_NAME = "trace_net_table_route_retrieval_demo_queries_v1.jsonl"
INSPECT_MD_NAME = "trace_net_table_route_retrieval_demo_query_pack_v1_inspect.md"

FIELD_EXPLANATIONS = {
    "covered_part_number": "This looks like a covered/effective part number from a table.",
    "ipl_part_number": "This looks like an illustrated-parts-list part number.",
    "manual_page_reference": "This points to a manual section or page reference.",
    "page_rev_or_sequence_value": "This looks like a page sequence or revision/table-list value.",
    "ipl_text": "This is descriptive table text from an illustrated-parts-list style table.",
    "ipl_figure_item_or_quantity": "This is a figure item, index, or quantity-style table value.",
}

FIELD_ANALOGIES = {
    "covered_part_number": "Like looking up a product SKU in a store inventory index.",
    "ipl_part_number": "Like searching a parts catalog by part number.",
    "manual_page_reference": "Like using a book index to jump to the right chapter/page.",
    "page_rev_or_sequence_value": "Like checking a table-of-contents line number or revision marker.",
    "ipl_text": "Like searching the notes column of a parts list.",
    "ipl_figure_item_or_quantity": "Like searching by item number on an exploded-view diagram list.",
}


def _read_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {p}")
    return data


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


def _summary(data: Mapping[str, Any]) -> Mapping[str, Any]:
    value = data.get("summary")
    return value if isinstance(value, Mapping) else data


def _int(data: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
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
                pass
    return 0


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass"}
    return bool(value)


def _quality_pass(data: Mapping[str, Any]) -> bool:
    value = data.get("quality_status", _summary(data).get("quality_status"))
    if isinstance(value, str):
        return value.upper() == QUALITY_PASS
    return bool(value)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _field_counts_from_summary(summary: Mapping[str, Any]) -> Dict[str, int]:
    value = summary.get("field_counts")
    if isinstance(value, Mapping):
        return {str(k): _int({"v": v}, "v") for k, v in value.items()}
    return {}


def _load_query_groups(bridge: Mapping[str, Any]) -> List[Dict[str, Any]]:
    value = bridge.get("query_bridge_groups")
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    value = bridge.get("query_groups")
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def _hit_field(hit: Mapping[str, Any]) -> str:
    return _clean_text(hit.get("field_name") or hit.get("field_role") or hit.get("field"))


def _hit_value(hit: Mapping[str, Any]) -> str:
    return _clean_text(
        hit.get("normalized_value")
        or hit.get("display_value")
        or hit.get("raw_value")
        or hit.get("value")
        or hit.get("text")
    )


def _hit_page(hit: Mapping[str, Any]) -> str:
    return _clean_text(hit.get("page_id") or hit.get("source_page_id"))


def _hit_boost(hit: Mapping[str, Any]) -> float:
    value = hit.get("routing_boost", hit.get("boost", 1.0))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def _query_intent_from_hits(hits: Sequence[Mapping[str, Any]]) -> str:
    fields = [_hit_field(hit) for hit in hits if _hit_field(hit)]
    if not fields:
        return "table_value_lookup"
    field, _count = Counter(fields).most_common(1)[0]
    return field or "table_value_lookup"


def _demo_query_from_group(group: Mapping[str, Any], index: int, top_k: int) -> Dict[str, Any]:
    raw_hits = group.get("hits")
    hits = [dict(hit) for hit in raw_hits if isinstance(hit, Mapping)] if isinstance(raw_hits, list) else []
    hits = hits[:top_k]
    query = _clean_text(group.get("query") or group.get("user_query") or group.get("search_query"))
    intent = _query_intent_from_hits(hits)
    pages = []
    seen_pages: Set[str] = set()
    for page in group.get("page_ids", []) if isinstance(group.get("page_ids"), list) else []:
        page_text = _clean_text(page)
        if page_text and page_text not in seen_pages:
            pages.append(page_text)
            seen_pages.add(page_text)
    for hit in hits:
        page = _hit_page(hit)
        if page and page not in seen_pages:
            pages.append(page)
            seen_pages.add(page)

    demo_hits: List[Dict[str, Any]] = []
    for hit in hits:
        field = _hit_field(hit)
        demo_hits.append(
            {
                "page_id": _hit_page(hit),
                "table_id": _clean_text(hit.get("table_id")),
                "field_name": field,
                "normalized_value": _hit_value(hit),
                "routing_boost": _hit_boost(hit),
                "retrieval_role": "ranking_signal_only",
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        )

    example_value = demo_hits[0]["normalized_value"] if demo_hits else ""
    example_field = demo_hits[0]["field_name"] if demo_hits else intent
    explanation = FIELD_EXPLANATIONS.get(example_field, "This query matched a table-route value.")
    analogy = FIELD_ANALOGIES.get(example_field, "Like a librarian finding the right index card, not writing the final answer.")

    return {
        "demo_query_id": f"table_demo_query_{index:03d}",
        "user_query": query,
        "query_intent": intent,
        "simple_explanation": explanation,
        "analogy": analogy,
        "matched_value_example": example_value,
        "match_count": _int(group, "match_count") or len(demo_hits),
        "page_ids": pages,
        "hit_count_in_demo": len(demo_hits),
        "hits": demo_hits,
        "retrieval_effect": "boost_matching_table_pages_in_hybrid_retrieval",
        "retrieval_permission": "ranking_only",
        "answer_authority": "blocked",
        "final_gate_required": True,
        "unsafe": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempted": False,
        "qdrant_write_attempted": False,
        "opensearch_write_attempted": False,
        "opensearch_upload_attempted": False,
    }


@dataclass(frozen=True)
class DemoPackThresholds:
    min_demo_queries: int = 3
    min_successful_demo_queries: int = 3
    min_total_demo_matches: int = 3
    min_pages_with_demo_matches: int = 1
    min_field_count: int = 4
    max_unsafe_records: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_source_readiness_quality_pass: bool = True
    require_source_bridge_quality_pass: bool = True
    require_readiness_status: bool = True
    require_no_answer_permission: bool = True


def evaluate_quality(summary: Mapping[str, Any], thresholds: DemoPackThresholds) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    add(
        "source_readiness_quality_pass",
        summary.get("source_readiness_quality_pass"),
        "is True",
        (not thresholds.require_source_readiness_quality_pass) or bool(summary.get("source_readiness_quality_pass")),
    )
    add(
        "source_bridge_quality_pass",
        summary.get("source_bridge_quality_pass"),
        "is True",
        (not thresholds.require_source_bridge_quality_pass) or bool(summary.get("source_bridge_quality_pass")),
    )
    add(
        "readiness_status_ready_for_ranking_only",
        summary.get("source_retrieval_readiness_status"),
        "READY_FOR_RETRIEVAL_RANKING_ONLY",
        (not thresholds.require_readiness_status)
        or summary.get("source_retrieval_readiness_status") == "READY_FOR_RETRIEVAL_RANKING_ONLY",
    )
    add("demo_query_count", _int(summary, "demo_query_count"), f">= {thresholds.min_demo_queries}", _int(summary, "demo_query_count") >= thresholds.min_demo_queries)
    add(
        "successful_demo_query_count",
        _int(summary, "successful_demo_query_count"),
        f">= {thresholds.min_successful_demo_queries}",
        _int(summary, "successful_demo_query_count") >= thresholds.min_successful_demo_queries,
    )
    add(
        "total_demo_match_count",
        _int(summary, "total_demo_match_count"),
        f">= {thresholds.min_total_demo_matches}",
        _int(summary, "total_demo_match_count") >= thresholds.min_total_demo_matches,
    )
    add(
        "page_with_demo_match_count",
        _int(summary, "page_with_demo_match_count"),
        f">= {thresholds.min_pages_with_demo_matches}",
        _int(summary, "page_with_demo_match_count") >= thresholds.min_pages_with_demo_matches,
    )
    add("field_count", _int(summary, "field_count"), f">= {thresholds.min_field_count}", _int(summary, "field_count") >= thresholds.min_field_count)
    add("unsafe_demo_record_count", _int(summary, "unsafe_demo_record_count"), f"<= {thresholds.max_unsafe_records}", _int(summary, "unsafe_demo_record_count") <= thresholds.max_unsafe_records)
    add("answer_permission_count", _int(summary, "answer_permission_count"), f"<= {thresholds.max_answer_permission_count}", _int(summary, "answer_permission_count") <= thresholds.max_answer_permission_count)
    add(
        "source_truth_mutation_allowed_count",
        _int(summary, "source_truth_mutation_allowed_count"),
        f"<= {thresholds.max_source_truth_mutation_allowed}",
        _int(summary, "source_truth_mutation_allowed_count") <= thresholds.max_source_truth_mutation_allowed,
    )
    add("can_answer_directly_count", _int(summary, "can_answer_directly_count"), "== 0", (not thresholds.require_no_answer_permission) or _int(summary, "can_answer_directly_count") == 0)
    add("can_prove_claims_count", _int(summary, "can_prove_claims_count"), "== 0", (not thresholds.require_no_answer_permission) or _int(summary, "can_prove_claims_count") == 0)
    add("postgres_write_attempt_count", _int(summary, "postgres_write_attempt_count"), "== 0", _int(summary, "postgres_write_attempt_count") == 0)
    add("qdrant_write_attempt_count", _int(summary, "qdrant_write_attempt_count"), "== 0", _int(summary, "qdrant_write_attempt_count") == 0)
    add("opensearch_write_attempt_count", _int(summary, "opensearch_write_attempt_count"), "== 0", _int(summary, "opensearch_write_attempt_count") == 0)
    add("opensearch_upload_attempt_count", _int(summary, "opensearch_upload_attempt_count"), "== 0", _int(summary, "opensearch_upload_attempt_count") == 0)
    return checks


def _build_inspect_md(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# TRACE-Net Table Route Retrieval Demo Query Pack v1 Inspect",
        "",
        f"Quality status: **{report['quality_status']}**",
        "",
        "## Demo purpose",
        "This artifact shows example table-route queries, the matched table values/pages, and the retrieval boost behavior.",
        "It is intentionally retrieval-only: the table values can help find evidence, but cannot answer directly.",
        "",
        "## Readiness contract",
    ]
    for key in [
        "source_retrieval_readiness_status",
        "demo_readiness_status",
        "retrieval_permission",
        "answer_authority",
        "ready_for_hybrid_retrieval_ranking",
        "ready_for_live_opensearch_upload",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Demo counters"])
    for key in [
        "demo_query_count",
        "successful_demo_query_count",
        "total_demo_match_count",
        "page_with_demo_match_count",
        "field_count",
        "source_bridge_record_count",
        "source_ranking_available_bridge_record_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Field counts"])
    field_counts = summary.get("field_counts") if isinstance(summary.get("field_counts"), Mapping) else {}
    for field, count in sorted(field_counts.items()):
        lines.append(f"- {field}: {count}")
    if not field_counts:
        lines.append("- none")
    lines.extend(["", "## Safety/write counters"])
    for key in [
        "unsafe_demo_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Demo queries"])
    for query in report.get("demo_queries", []):
        lines.append(f"- query='{query['user_query']}' matches={query['match_count']} pages={','.join(query['page_ids'][:10])}")
        lines.append(f"  - analogy: {query['analogy']}")
        for hit in query.get("hits", [])[:5]:
            lines.append(
                f"  - {hit['page_id']} | {hit['field_name']} | {hit['normalized_value']} | boost={hit['routing_boost']}"
            )
    lines.extend(["", "## Quality checks"])
    for check in report.get("quality_checks", []):
        status = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {status} {check['name']}: observed={check['observed']} expected={check['expected']}")
    return "\n".join(lines) + "\n"


def build_demo_query_pack(
    *,
    table_route_retrieval_readiness_report_path: str | Path,
    table_hybrid_retrieval_bridge_path: str | Path,
    output_dir: str | Path,
    top_k: int = 5,
    thresholds: DemoPackThresholds | None = None,
) -> Dict[str, Any]:
    thresholds = thresholds or DemoPackThresholds()
    readiness_path = Path(table_route_retrieval_readiness_report_path)
    bridge_path = Path(table_hybrid_retrieval_bridge_path)
    out_dir = Path(output_dir)

    readiness = _read_json(readiness_path)
    bridge = _read_json(bridge_path)
    readiness_summary = _summary(readiness)
    bridge_summary = _summary(bridge)
    query_groups = _load_query_groups(bridge)

    demo_queries = [_demo_query_from_group(group, index + 1, top_k) for index, group in enumerate(query_groups)]
    demo_queries = [query for query in demo_queries if query["user_query"]]

    pages: Set[str] = set()
    fields: Counter[str] = Counter()
    total_matches = 0
    for query in demo_queries:
        total_matches += _int(query, "match_count")
        for page in query.get("page_ids", []):
            if page:
                pages.add(str(page))
        for hit in query.get("hits", []):
            field = hit.get("field_name")
            if field:
                fields[str(field)] += 1

    source_field_counts = _field_counts_from_summary(readiness_summary) or _field_counts_from_summary(bridge_summary)
    field_count = len(source_field_counts) if source_field_counts else len(fields)

    unsafe_count = sum(1 for query in demo_queries if _truthy(query.get("unsafe")))
    answer_permission_count = sum(1 for query in demo_queries if _truthy(query.get("answer_permission")))
    can_answer_count = sum(1 for query in demo_queries if _truthy(query.get("can_answer_directly")))
    can_prove_count = sum(1 for query in demo_queries if _truthy(query.get("can_prove_claims")))
    mutation_count = sum(1 for query in demo_queries if _truthy(query.get("source_truth_mutation_allowed")))

    summary: Dict[str, Any] = {
        "source_readiness_path": str(readiness_path),
        "source_bridge_path": str(bridge_path),
        "source_readiness_quality_pass": _quality_pass(readiness),
        "source_bridge_quality_pass": _quality_pass(bridge),
        "source_retrieval_readiness_status": readiness_summary.get("retrieval_readiness_status"),
        "source_exact_search_document_count": _int(readiness_summary, "exact_search_document_count"),
        "source_successful_smoke_query_count": _int(readiness_summary, "successful_smoke_query_count"),
        "source_total_smoke_match_count": _int(readiness_summary, "total_smoke_match_count"),
        "source_bridge_record_count": _int(readiness_summary, "bridge_record_count", "source_bridge_record_count") or _int(bridge_summary, "table_hybrid_bridge_record_count", "source_bridge_record_count"),
        "source_ranking_available_bridge_record_count": _int(readiness_summary, "ranking_available_bridge_record_count"),
        "demo_readiness_status": "DEMO_READY_RETRIEVAL_ONLY",
        "retrieval_permission": "ranking_only",
        "answer_authority": "blocked",
        "ready_for_hybrid_retrieval_ranking": bool(readiness_summary.get("ready_for_hybrid_retrieval_ranking", True)),
        "ready_for_live_opensearch_upload": False,
        "demo_query_count": len(demo_queries),
        "successful_demo_query_count": sum(1 for query in demo_queries if _int(query, "match_count") > 0),
        "total_demo_match_count": total_matches,
        "page_with_demo_match_count": len(pages),
        "field_count": field_count,
        "field_counts": source_field_counts or dict(fields),
        "unsafe_demo_record_count": unsafe_count,
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": can_answer_count,
        "can_prove_claims_count": can_prove_count,
        "source_truth_mutation_allowed_count": mutation_count,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }
    checks = evaluate_quality(summary, thresholds)
    quality_status = QUALITY_PASS if all(check["passed"] for check in checks) else QUALITY_FAIL

    report: Dict[str, Any] = {
        "schema_version": "trace_net_table_route_retrieval_demo_query_pack_v1",
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "summary": summary,
        "readiness_contract": {
            "table_route_values_are_searchable": True,
            "table_route_values_are_ranking_signals": True,
            "retrieval_permission": "ranking_only",
            "answer_authority": "blocked",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
        },
        "demo_queries": demo_queries,
        "quality_checks": checks,
    }

    report_path = out_dir / REPORT_NAME
    quality_path = out_dir / QUALITY_NAME
    demo_jsonl_path = out_dir / DEMO_JSONL_NAME
    inspect_path = out_dir / INSPECT_MD_NAME
    report["report_path"] = str(report_path)
    report["quality_json_path"] = str(quality_path)
    report["demo_queries_jsonl_path"] = str(demo_jsonl_path)
    report["inspect_md_path"] = str(inspect_path)

    _write_json(report_path, report)
    _write_json(quality_path, {"quality_status": quality_status, "summary": summary, "quality_checks": checks})
    _write_jsonl(demo_jsonl_path, demo_queries)
    inspect_path.parent.mkdir(parents=True, exist_ok=True)
    inspect_path.write_text(_build_inspect_md(report), encoding="utf-8")
    return report


def add_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-demo-queries", type=int, default=3)
    parser.add_argument("--min-successful-demo-queries", type=int, default=3)
    parser.add_argument("--min-total-demo-matches", type=int, default=3)
    parser.add_argument("--min-pages-with-demo-matches", type=int, default=1)
    parser.add_argument("--min-field-count", type=int, default=4)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-readiness-quality-pass", action="store_true")
    parser.add_argument("--require-source-bridge-quality-pass", action="store_true")
    parser.add_argument("--require-readiness-status", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def thresholds_from_args(args: argparse.Namespace) -> DemoPackThresholds:
    return DemoPackThresholds(
        min_demo_queries=args.min_demo_queries,
        min_successful_demo_queries=args.min_successful_demo_queries,
        min_total_demo_matches=args.min_total_demo_matches,
        min_pages_with_demo_matches=args.min_pages_with_demo_matches,
        min_field_count=args.min_field_count,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_source_readiness_quality_pass=args.require_source_readiness_quality_pass,
        require_source_bridge_quality_pass=args.require_source_bridge_quality_pass,
        require_readiness_status=args.require_readiness_status,
        require_no_answer_permission=args.require_no_answer_permission,
    )
