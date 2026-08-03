"""TRACE-Net table hybrid retrieval bridge v1.

Builds local retrieval-bridge records from table exact-search artifacts and the
local exact-search smoke report. The bridge lets table-route evidence participate
in hybrid retrieval ranking as retrieval-only signals. It never grants answer
authority and never writes to Postgres, Qdrant, OpenSearch, or live services.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

STATUS_BUILT = "TABLE_HYBRID_RETRIEVAL_BRIDGE_BUILT"
STATUS_NOT_READY = "TABLE_HYBRID_RETRIEVAL_BRIDGE_NOT_READY"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

REPORT_NAME = "trace_net_table_hybrid_retrieval_bridge_v1.json"
QUALITY_NAME = "trace_net_table_hybrid_retrieval_bridge_v1_quality.json"
BRIDGE_JSONL_NAME = "trace_net_table_hybrid_retrieval_bridge_records_v1.jsonl"
GROUPS_JSONL_NAME = "trace_net_table_hybrid_retrieval_bridge_query_groups_v1.jsonl"
INSPECT_MD_NAME = "trace_net_table_hybrid_retrieval_bridge_v1_inspect.md"

FALSE_VALUES = {False, 0, "0", "false", "False", "FALSE", "no", "No", "NO", ""}
TRUE_VALUES = {True, 1, "1", "true", "True", "TRUE", "yes", "Yes", "YES"}

FIELD_BOOSTS = {
    "covered_part_number": 1.35,
    "ipl_part_number": 1.30,
    "manual_page_reference": 1.25,
    "page_rev_or_sequence_value": 1.05,
    "ipl_text": 1.00,
    "ipl_figure_item_or_quantity": 0.95,
}

SAFETY_FLAGS = (
    "unsafe",
    "is_unsafe",
    "unsafe_record",
    "answer_permission",
    "can_answer_directly",
    "can_prove_claims",
    "source_truth_mutation_allowed",
    "postgres_write_attempted",
    "qdrant_write_attempted",
    "opensearch_write_attempted",
    "opensearch_upload_attempted",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "opensearch_upload_attempt_count",
)

SEARCH_TEXT_FIELDS = (
    "normalized_value",
    "raw_value",
    "display_value",
    "field_name",
    "field_role",
    "page_id",
    "source_page_id",
    "table_id",
    "row_id",
    "cell_id",
    "table_template",
    "search_text",
)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, Mapping):
                rows.append(dict(row))
    return rows


def _truthy(value: Any) -> bool:
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES or value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    return bool(value)


def _stable_hash(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:16]


def _normalize_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.\-/]*", text or "")
    seen = set()
    out: List[str] = []
    for token in tokens:
        low = token.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(token)
    return out[:80]


def _source_summary(report: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = report.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _quality_pass(report: Mapping[str, Any]) -> bool:
    status = str(report.get("quality_status", _source_summary(report).get("quality_status", ""))).upper()
    if status == QUALITY_PASS:
        return True
    return bool(_source_summary(report).get("quality_pass") is True)


def _find_jsonl_path(report: Mapping[str, Any], report_path: Path, names: Sequence[str], fallback_name: str) -> Optional[Path]:
    candidates: List[Any] = []
    for name in names:
        candidates.append(report.get(name))
    paths = report.get("paths")
    if isinstance(paths, Mapping):
        for name in names:
            candidates.append(paths.get(name))
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate))
        if path.is_absolute() and path.exists():
            return path
        if not path.is_absolute():
            if path.exists():
                return path
            sibling = report_path.parent / path.name
            if sibling.exists():
                return sibling
    fallback = report_path.parent / fallback_name
    if fallback.exists():
        return fallback
    return None


def load_exact_search_documents(adapter_path: Path) -> Tuple[Mapping[str, Any], List[Dict[str, Any]], str]:
    adapter = _read_json(adapter_path)
    if not isinstance(adapter, Mapping):
        raise ValueError(f"Expected JSON object at {adapter_path}")
    for key in ("exact_search_documents", "table_exact_search_documents", "documents", "records"):
        value = adapter.get(key)
        if isinstance(value, list):
            return adapter, [dict(row) for row in value if isinstance(row, Mapping)], key
    jsonl_path = _find_jsonl_path(
        adapter,
        adapter_path,
        ("exact_search_jsonl_path", "exact_search_documents_jsonl_path", "table_exact_search_documents_jsonl_path"),
        "trace_net_table_exact_search_documents_v1.jsonl",
    )
    if jsonl_path is not None:
        return adapter, _read_jsonl(jsonl_path), str(jsonl_path)
    return adapter, [], "none"


def load_smoke_results(smoke_path: Path) -> Tuple[Mapping[str, Any], List[Dict[str, Any]], str]:
    smoke = _read_json(smoke_path)
    if not isinstance(smoke, Mapping):
        raise ValueError(f"Expected JSON object at {smoke_path}")
    for key in ("smoke_results", "results", "query_results", "records"):
        value = smoke.get(key)
        if isinstance(value, list):
            return smoke, [dict(row) for row in value if isinstance(row, Mapping)], key
    jsonl_path = _find_jsonl_path(
        smoke,
        smoke_path,
        ("smoke_results_jsonl_path", "results_jsonl_path"),
        "trace_net_table_exact_search_smoke_results_v1.jsonl",
    )
    if jsonl_path is not None:
        return smoke, _read_jsonl(jsonl_path), str(jsonl_path)
    return smoke, [], "none"


def _doc_is_safe(doc: Mapping[str, Any]) -> bool:
    for flag in SAFETY_FLAGS:
        if _truthy(doc.get(flag)):
            return False
    return _truthy(doc.get("retrieval_only", True))


def _bridge_search_text(doc: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in SEARCH_TEXT_FIELDS:
        value = doc.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value if item is not None)
        elif value is not None:
            parts.append(str(value))
    tokens = doc.get("search_tokens")
    if isinstance(tokens, list):
        parts.extend(str(token) for token in tokens if token is not None)
    return _normalize_text(" | ".join(parts))


def make_bridge_record(doc: Mapping[str, Any], ordinal: int) -> Optional[Dict[str, Any]]:
    if not _doc_is_safe(doc):
        return None
    field_name = _normalize_text(doc.get("field_name") or doc.get("field_role") or doc.get("field") or "")
    normalized_value = _normalize_text(doc.get("normalized_value") or doc.get("value") or doc.get("display_value") or doc.get("raw_value") or "")
    page_id = _normalize_text(doc.get("page_id") or doc.get("source_page_id") or "")
    if not field_name or not normalized_value or not page_id:
        return None
    base_payload = {
        "document_id": doc.get("document_id", ""),
        "page_id": page_id,
        "table_id": doc.get("table_id", ""),
        "field_name": field_name,
        "normalized_value": normalized_value,
        "ordinal": ordinal,
    }
    boost = float(FIELD_BOOSTS.get(field_name, 1.0))
    bridge_text = _bridge_search_text(doc)
    if not bridge_text:
        bridge_text = f"{field_name} {normalized_value} {page_id}"
    return {
        "bridge_record_id": f"table_hybrid_bridge::{_stable_hash(base_payload)}",
        "source_exact_search_document_id": doc.get("document_id", ""),
        "page_id": page_id,
        "source_page_id": doc.get("source_page_id", page_id),
        "table_id": doc.get("table_id", ""),
        "row_id": doc.get("row_id", ""),
        "cell_id": doc.get("cell_id", ""),
        "field_name": field_name,
        "normalized_value": normalized_value,
        "raw_value": doc.get("raw_value", normalized_value),
        "table_template": doc.get("table_template", ""),
        "route": "table",
        "retrieval_channel": "table_exact_search",
        "hybrid_retrieval_role": "ranking_signal_only",
        "routing_boost": boost,
        "bridge_text": bridge_text,
        "search_tokens": _tokenize(bridge_text),
        "retrieval_only": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "unsafe": False,
        "postgres_write_attempted": False,
        "qdrant_write_attempted": False,
        "opensearch_write_attempted": False,
        "opensearch_upload_attempted": False,
    }


def build_bridge_records(docs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for idx, doc in enumerate(docs):
        record = make_bridge_record(doc, idx)
        if record is not None:
            records.append(record)
    return records


def _index_bridge_records(records: Sequence[Mapping[str, Any]]) -> Dict[Tuple[str, str, str], List[Mapping[str, Any]]]:
    index: Dict[Tuple[str, str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        key = (
            str(record.get("page_id", "")),
            str(record.get("field_name", "")),
            str(record.get("normalized_value", "")),
        )
        index[key].append(record)
    return index


def build_query_groups(smoke_results: Sequence[Mapping[str, Any]], bridge_records: Sequence[Mapping[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
    index = _index_bridge_records(bridge_records)
    groups: List[Dict[str, Any]] = []
    for result in smoke_results:
        query = str(result.get("query", ""))
        hits = result.get("hits") if isinstance(result.get("hits"), list) else []
        bridge_hits: List[Dict[str, Any]] = []
        for hit in hits:
            if not isinstance(hit, Mapping):
                continue
            key = (
                str(hit.get("page_id", "")),
                str(hit.get("field_name", "")),
                str(hit.get("normalized_value", "")),
            )
            for record in index.get(key, [])[:1]:
                bridge_hits.append(
                    {
                        "bridge_record_id": record.get("bridge_record_id", ""),
                        "page_id": record.get("page_id", ""),
                        "field_name": record.get("field_name", ""),
                        "normalized_value": record.get("normalized_value", ""),
                        "retrieval_channel": record.get("retrieval_channel", "table_exact_search"),
                        "routing_boost": record.get("routing_boost", 1.0),
                        "smoke_score": hit.get("score", 0),
                        "retrieval_only": True,
                        "answer_permission": False,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                        "source_truth_mutation_allowed": False,
                    }
                )
            if len(bridge_hits) >= top_k:
                break
        pages = sorted({str(hit.get("page_id")) for hit in bridge_hits if hit.get("page_id")})
        fields = sorted({str(hit.get("field_name")) for hit in bridge_hits if hit.get("field_name")})
        groups.append(
            {
                "query": query,
                "group_id": f"table_hybrid_query_group::{_stable_hash({'query': query, 'pages': pages, 'fields': fields})}",
                "hybrid_retrieval_role": "ranking_signal_only",
                "retrieval_channel": "table_exact_search_smoke",
                "match_count": len(bridge_hits),
                "page_ids": pages,
                "field_names": fields,
                "hits": bridge_hits,
                "retrieval_only": True,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        )
    return groups


def _quality_checks(summary: Mapping[str, Any], args: argparse.Namespace) -> List[Dict[str, Any]]:
    def check(name: str, observed: Any, op: str, expected: Any, passed: bool) -> Dict[str, Any]:
        return {"name": name, "observed": observed, "operator": op, "expected": expected, "passed": bool(passed)}

    return [
        check("source_exact_search_adapter_quality_pass", summary.get("source_exact_search_adapter_quality_pass"), "is True", True, (not args.require_source_exact_search_adapter_quality_pass) or bool(summary.get("source_exact_search_adapter_quality_pass"))),
        check("source_exact_search_smoke_quality_pass", summary.get("source_exact_search_smoke_quality_pass"), "is True", True, (not args.require_source_exact_search_smoke_quality_pass) or bool(summary.get("source_exact_search_smoke_quality_pass"))),
        check("source_exact_search_document_count", summary.get("source_exact_search_document_count", 0), ">=", args.min_source_exact_search_documents, int(summary.get("source_exact_search_document_count", 0)) >= args.min_source_exact_search_documents),
        check("source_successful_smoke_query_count", summary.get("source_successful_smoke_query_count", 0), ">=", args.min_source_successful_smoke_queries, int(summary.get("source_successful_smoke_query_count", 0)) >= args.min_source_successful_smoke_queries),
        check("table_hybrid_bridge_record_count", summary.get("table_hybrid_bridge_record_count", 0), ">=", args.min_bridge_records, int(summary.get("table_hybrid_bridge_record_count", 0)) >= args.min_bridge_records),
        check("page_with_bridge_record_count", summary.get("page_with_bridge_record_count", 0), ">=", args.min_pages_with_bridge_records, int(summary.get("page_with_bridge_record_count", 0)) >= args.min_pages_with_bridge_records),
        check("field_count", summary.get("field_count", 0), ">=", args.min_field_count, int(summary.get("field_count", 0)) >= args.min_field_count),
        check("query_bridge_group_count", summary.get("query_bridge_group_count", 0), ">=", args.min_query_bridge_groups, int(summary.get("query_bridge_group_count", 0)) >= args.min_query_bridge_groups),
        check("successful_query_bridge_group_count", summary.get("successful_query_bridge_group_count", 0), ">=", args.min_successful_query_bridge_groups, int(summary.get("successful_query_bridge_group_count", 0)) >= args.min_successful_query_bridge_groups),
        check("covered_part_number_bridge_records", summary.get("field_counts", {}).get("covered_part_number", 0), ">=", args.min_covered_part_number_bridge_records, int(summary.get("field_counts", {}).get("covered_part_number", 0)) >= args.min_covered_part_number_bridge_records),
        check("manual_page_reference_bridge_records", summary.get("field_counts", {}).get("manual_page_reference", 0), ">=", args.min_manual_page_reference_bridge_records, int(summary.get("field_counts", {}).get("manual_page_reference", 0)) >= args.min_manual_page_reference_bridge_records),
        check("ipl_part_number_bridge_records", summary.get("field_counts", {}).get("ipl_part_number", 0), ">=", args.min_ipl_part_number_bridge_records, int(summary.get("field_counts", {}).get("ipl_part_number", 0)) >= args.min_ipl_part_number_bridge_records),
        check("unsafe_bridge_record_count", summary.get("unsafe_bridge_record_count", 0), "<=", args.max_unsafe_records, int(summary.get("unsafe_bridge_record_count", 0)) <= args.max_unsafe_records),
        check("answer_permission_count", summary.get("answer_permission_count", 0), "<=", args.max_answer_permission_count, int(summary.get("answer_permission_count", 0)) <= args.max_answer_permission_count),
        check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), "<=", args.max_source_truth_mutation_allowed, int(summary.get("source_truth_mutation_allowed_count", 0)) <= args.max_source_truth_mutation_allowed),
        check("can_answer_directly_count", summary.get("can_answer_directly_count", 0), "==", 0, int(summary.get("can_answer_directly_count", 0)) == 0),
        check("can_prove_claims_count", summary.get("can_prove_claims_count", 0), "==", 0, int(summary.get("can_prove_claims_count", 0)) == 0),
        check("postgres_write_attempt_count", summary.get("postgres_write_attempt_count", 0), "==", 0, int(summary.get("postgres_write_attempt_count", 0)) == 0),
        check("qdrant_write_attempt_count", summary.get("qdrant_write_attempt_count", 0), "==", 0, int(summary.get("qdrant_write_attempt_count", 0)) == 0),
        check("opensearch_write_attempt_count", summary.get("opensearch_write_attempt_count", 0), "==", 0, int(summary.get("opensearch_write_attempt_count", 0)) == 0),
        check("opensearch_upload_attempt_count", summary.get("opensearch_upload_attempt_count", 0), "==", 0, int(summary.get("opensearch_upload_attempt_count", 0)) == 0),
    ]


def _write_inspect_md(path: Path, report: Mapping[str, Any]) -> None:
    summary = report.get("summary") or {}
    field_counts = summary.get("field_counts") or {}
    groups = report.get("query_bridge_groups") or []
    records = report.get("bridge_records") or []
    lines = [
        "# TRACE-Net Table Hybrid Retrieval Bridge v1 Inspect",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        "",
        "## Bridge counters",
        f"- source_exact_search_document_count: {summary.get('source_exact_search_document_count', 0)}",
        f"- table_hybrid_bridge_record_count: {summary.get('table_hybrid_bridge_record_count', 0)}",
        f"- page_with_bridge_record_count: {summary.get('page_with_bridge_record_count', 0)}",
        f"- field_count: {summary.get('field_count', 0)}",
        f"- query_bridge_group_count: {summary.get('query_bridge_group_count', 0)}",
        f"- successful_query_bridge_group_count: {summary.get('successful_query_bridge_group_count', 0)}",
        "",
        "## Field counts",
    ]
    if field_counts:
        for field, count in sorted(field_counts.items()):
            lines.append(f"- {field}: {count}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Safety/write counters",
            f"- unsafe_bridge_record_count: {summary.get('unsafe_bridge_record_count', 0)}",
            f"- answer_permission_count: {summary.get('answer_permission_count', 0)}",
            f"- can_answer_directly_count: {summary.get('can_answer_directly_count', 0)}",
            f"- can_prove_claims_count: {summary.get('can_prove_claims_count', 0)}",
            f"- source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count', 0)}",
            f"- postgres_write_attempt_count: {summary.get('postgres_write_attempt_count', 0)}",
            f"- qdrant_write_attempt_count: {summary.get('qdrant_write_attempt_count', 0)}",
            f"- opensearch_write_attempt_count: {summary.get('opensearch_write_attempt_count', 0)}",
            f"- opensearch_upload_attempt_count: {summary.get('opensearch_upload_attempt_count', 0)}",
            "",
            "## Query bridge groups",
        ]
    )
    if not groups:
        lines.append("No query bridge groups generated.")
    for group in groups[:10]:
        lines.append(f"- query={group.get('query')!r} matches={group.get('match_count', 0)} pages={','.join(group.get('page_ids') or [])}")
        for hit in (group.get("hits") or [])[:5]:
            lines.append(f"  - {hit.get('page_id')} | {hit.get('field_name')} | {hit.get('normalized_value')} | boost={hit.get('routing_boost')}")
    lines.extend(["", "## First bridge records"])
    if not records:
        lines.append("No bridge records generated.")
    for record in records[:20]:
        lines.append(f"- {record.get('page_id')} | {record.get('field_name')} | {record.get('normalized_value')} | boost={record.get('routing_boost')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_table_hybrid_retrieval_bridge(
    table_exact_search_adapter: Path,
    table_exact_search_smoke: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter, docs, source_collection = load_exact_search_documents(table_exact_search_adapter)
    smoke, smoke_results, smoke_collection = load_smoke_results(table_exact_search_smoke)
    adapter_summary = _source_summary(adapter)
    smoke_summary = _source_summary(smoke)

    bridge_records = build_bridge_records(docs)
    query_groups = build_query_groups(smoke_results, bridge_records, top_k=args.top_k)

    pages = {record.get("page_id") for record in bridge_records if record.get("page_id")}
    tables = {record.get("table_id") for record in bridge_records if record.get("table_id")}
    fields = Counter(record.get("field_name") for record in bridge_records if record.get("field_name"))
    all_group_hits = [hit for group in query_groups for hit in (group.get("hits") or [])]

    summary: Dict[str, Any] = {
        "source_exact_search_adapter_path": str(table_exact_search_adapter),
        "source_exact_search_smoke_path": str(table_exact_search_smoke),
        "source_exact_search_collection": source_collection,
        "source_smoke_collection": smoke_collection,
        "source_exact_search_adapter_quality_pass": _quality_pass(adapter),
        "source_exact_search_smoke_quality_pass": _quality_pass(smoke),
        "source_exact_search_document_count": len(docs),
        "source_table_exact_search_document_count": adapter_summary.get("table_exact_search_document_count", len(docs)),
        "source_successful_smoke_query_count": smoke_summary.get("successful_smoke_query_count", sum(1 for row in smoke_results if int(row.get("match_count", 0)) > 0)),
        "source_total_smoke_match_count": smoke_summary.get("total_match_count", sum(int(row.get("match_count", 0)) for row in smoke_results)),
        "table_hybrid_bridge_record_count": len(bridge_records),
        "page_with_bridge_record_count": len(pages),
        "table_with_bridge_record_count": len(tables),
        "field_count": len(fields),
        "field_counts": dict(sorted(fields.items())),
        "query_bridge_group_count": len(query_groups),
        "successful_query_bridge_group_count": sum(1 for group in query_groups if int(group.get("match_count", 0)) > 0),
        "total_query_bridge_hit_count": len(all_group_hits),
        "retrieval_only_bridge_record_count": sum(1 for record in bridge_records if _truthy(record.get("retrieval_only"))),
        "unsafe_bridge_record_count": sum(1 for record in bridge_records if _truthy(record.get("unsafe"))),
        "answer_permission_count": sum(1 for record in bridge_records if _truthy(record.get("answer_permission"))) + sum(1 for hit in all_group_hits if _truthy(hit.get("answer_permission"))),
        "can_answer_directly_count": sum(1 for record in bridge_records if _truthy(record.get("can_answer_directly"))) + sum(1 for hit in all_group_hits if _truthy(hit.get("can_answer_directly"))),
        "can_prove_claims_count": sum(1 for record in bridge_records if _truthy(record.get("can_prove_claims"))) + sum(1 for hit in all_group_hits if _truthy(hit.get("can_prove_claims"))),
        "source_truth_mutation_allowed_count": sum(1 for record in bridge_records if _truthy(record.get("source_truth_mutation_allowed"))) + sum(1 for hit in all_group_hits if _truthy(hit.get("source_truth_mutation_allowed"))),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }
    checks = _quality_checks(summary, args)
    quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL

    report_path = output_dir / REPORT_NAME
    bridge_jsonl_path = output_dir / BRIDGE_JSONL_NAME
    groups_jsonl_path = output_dir / GROUPS_JSONL_NAME
    inspect_md_path = output_dir / INSPECT_MD_NAME
    report: Dict[str, Any] = {
        "status": STATUS_BUILT if bridge_records else STATUS_NOT_READY,
        "quality_status": quality_status,
        "summary": summary,
        "quality_checks": checks,
        "paths": {
            "report_path": str(report_path),
            "bridge_jsonl_path": str(bridge_jsonl_path),
            "query_groups_jsonl_path": str(groups_jsonl_path),
            "inspect_md_path": str(inspect_md_path),
        },
        "bridge_records": bridge_records,
        "query_bridge_groups": query_groups,
    }
    _write_json(report_path, report)
    _write_jsonl(bridge_jsonl_path, bridge_records)
    _write_jsonl(groups_jsonl_path, query_groups)
    _write_inspect_md(inspect_md_path, report)
    return report


def add_common_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-source-exact-search-documents", type=int, default=1000)
    parser.add_argument("--min-source-successful-smoke-queries", type=int, default=3)
    parser.add_argument("--min-bridge-records", type=int, default=1000)
    parser.add_argument("--min-pages-with-bridge-records", type=int, default=1)
    parser.add_argument("--min-field-count", type=int, default=4)
    parser.add_argument("--min-query-bridge-groups", type=int, default=3)
    parser.add_argument("--min-successful-query-bridge-groups", type=int, default=3)
    parser.add_argument("--min-covered-part-number-bridge-records", type=int, default=100)
    parser.add_argument("--min-manual-page-reference-bridge-records", type=int, default=39)
    parser.add_argument("--min-ipl-part-number-bridge-records", type=int, default=100)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-exact-search-adapter-quality-pass", action="store_true")
    parser.add_argument("--require-source-exact-search-smoke-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table hybrid retrieval bridge v1.")
    parser.add_argument("--table-exact-search-adapter", required=True, type=Path)
    parser.add_argument("--table-exact-search-smoke", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--quality", action="store_true")
    add_common_quality_args(parser)
    return parser


def check_quality_report(report: Mapping[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    summary = report.get("summary") or {}
    checks = _quality_checks(summary, args)
    quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    return {
        "status": report.get("status", STATUS_NOT_READY),
        "quality_status": quality_status,
        "summary": summary,
        "quality_checks": checks,
    }


def quality_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table hybrid retrieval bridge v1 quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    add_common_quality_args(parser)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_table_hybrid_retrieval_bridge(args.table_exact_search_adapter, args.table_exact_search_smoke, args.output_dir, args)
    summary = report["summary"]
    print("TRACE-Net Table Hybrid Retrieval Bridge v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in (
        "source_exact_search_document_count",
        "source_successful_smoke_query_count",
        "table_hybrid_bridge_record_count",
        "page_with_bridge_record_count",
        "table_with_bridge_record_count",
        "field_count",
        "query_bridge_group_count",
        "successful_query_bridge_group_count",
        "total_query_bridge_hit_count",
        "unsafe_bridge_record_count",
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
    for name, path in report["paths"].items():
        print(f" {name}: {path}")
    if args.quality and report["quality_status"] != QUALITY_PASS:
        return 1
    return 0


def quality_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = quality_parser()
    args = parser.parse_args(argv)
    report = _read_json(args.report_path)
    quality = check_quality_report(report, args)
    if args.write_json:
        _write_json(args.report_path.parent / QUALITY_NAME, quality)
    print("TRACE-Net Table Hybrid Retrieval Bridge v1 Quality")
    print(f" quality_status: {quality['quality_status']}")
    for check in quality["quality_checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f" {status} {check['name']}: observed={check['observed']} expected={check['operator']} {check['expected']}")
    return 0 if quality["quality_status"] == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
