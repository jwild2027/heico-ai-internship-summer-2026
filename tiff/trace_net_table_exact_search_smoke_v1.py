"""TRACE-Net table exact-search smoke v1.

Runs a local-only smoke search over table exact-search JSONL documents before any
live OpenSearch upload. This module proves that generated table exact-search
artifacts can retrieve known values while keeping every result retrieval-only.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

STATUS_BUILT = "TABLE_EXACT_SEARCH_SMOKE_BUILT"
STATUS_NOT_READY = "TABLE_EXACT_SEARCH_SMOKE_NOT_READY"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

REPORT_NAME = "trace_net_table_exact_search_smoke_v1.json"
QUALITY_NAME = "trace_net_table_exact_search_smoke_v1_quality.json"
RESULTS_JSONL_NAME = "trace_net_table_exact_search_smoke_results_v1.jsonl"
INSPECT_MD_NAME = "trace_net_table_exact_search_smoke_v1_inspect.md"

FALSE_VALUES = {False, 0, "0", "false", "False", "FALSE", "no", "No", "NO", ""}
TRUE_VALUES = {True, 1, "1", "true", "True", "TRUE", "yes", "Yes", "YES"}

PREFERRED_AUTO_FIELDS = (
    "covered_part_number",
    "manual_page_reference",
    "ipl_part_number",
    "page_rev_or_sequence_value",
    "ipl_text",
    "ipl_figure_item_or_quantity",
)

SEARCH_FIELDS = (
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

SAFETY_FLAGS = (
    "unsafe",
    "answer_permission",
    "can_answer_directly",
    "can_prove_claims",
    "source_truth_mutation_allowed",
    "postgres_write_attempted",
    "qdrant_write_attempted",
    "opensearch_write_attempted",
    "opensearch_upload_attempted",
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


def _source_quality_pass(adapter: Mapping[str, Any]) -> bool:
    status = str(adapter.get("quality_status", adapter.get("summary", {}).get("quality_status", ""))).upper()
    if status == QUALITY_PASS:
        return True
    summary = adapter.get("summary") or {}
    return bool(summary.get("source_evidence_package_quality_pass") is True or summary.get("quality_status") == QUALITY_PASS)


def _source_summary(adapter: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = adapter.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _find_exact_search_jsonl_path(adapter: Mapping[str, Any], report_path: Path) -> Optional[Path]:
    candidates: List[Any] = [
        adapter.get("exact_search_jsonl_path"),
        adapter.get("exact_search_documents_jsonl_path"),
        adapter.get("table_exact_search_documents_jsonl_path"),
    ]
    paths = adapter.get("paths")
    if isinstance(paths, Mapping):
        candidates.extend(
            [
                paths.get("exact_search_jsonl_path"),
                paths.get("exact_search_documents_jsonl_path"),
                paths.get("table_exact_search_documents_jsonl_path"),
            ]
        )
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
    fallback = report_path.parent / "trace_net_table_exact_search_documents_v1.jsonl"
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
    jsonl_path = _find_exact_search_jsonl_path(adapter, adapter_path)
    if jsonl_path is not None:
        return adapter, _read_jsonl(jsonl_path), str(jsonl_path)
    return adapter, [], "none"


def _normalize_query(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9][a-z0-9_.\-/]*", _normalize_query(text))


def _doc_search_blob(doc: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in SEARCH_FIELDS:
        value = doc.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value if item is not None)
        elif value is not None:
            parts.append(str(value))
    tokens = doc.get("search_tokens")
    if isinstance(tokens, list):
        parts.extend(str(token) for token in tokens if token is not None)
    return _normalize_query(" | ".join(parts))


def _doc_is_safe_retrieval_only(doc: Mapping[str, Any]) -> bool:
    for flag in SAFETY_FLAGS:
        if _truthy(doc.get(flag)):
            return False
    return _truthy(doc.get("retrieval_only", True))


def score_document(query: str, doc: Mapping[str, Any]) -> int:
    query_norm = _normalize_query(query)
    if not query_norm:
        return 0
    blob = _doc_search_blob(doc)
    score = 0
    if query_norm in blob:
        score += 100
    for token in _tokenize(query_norm):
        if token in blob:
            score += 10
    field_name = _normalize_query(str(doc.get("field_name", "")))
    value = _normalize_query(str(doc.get("normalized_value", "")))
    if query_norm and query_norm == value:
        score += 75
    if query_norm and query_norm == field_name:
        score += 50
    return score


def search_documents(query: str, docs: Sequence[Mapping[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
    hits: List[Tuple[int, int, Mapping[str, Any]]] = []
    for idx, doc in enumerate(docs):
        if not _doc_is_safe_retrieval_only(doc):
            continue
        score = score_document(query, doc)
        if score > 0:
            hits.append((score, idx, doc))
    hits.sort(key=lambda item: (-item[0], item[1]))
    results: List[Dict[str, Any]] = []
    for score, _, doc in hits[:top_k]:
        results.append(
            {
                "score": score,
                "document_id": doc.get("document_id", ""),
                "page_id": doc.get("page_id", ""),
                "table_id": doc.get("table_id", ""),
                "field_name": doc.get("field_name", ""),
                "normalized_value": doc.get("normalized_value", ""),
                "retrieval_only": True,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        )
    return results


def derive_auto_queries(docs: Sequence[Mapping[str, Any]], limit: int = 6) -> List[str]:
    queries: List[str] = []
    seen = set()

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        queries.append(text)

    by_field: Dict[str, List[Mapping[str, Any]]] = {}
    for doc in docs:
        field = str(doc.get("field_name", "")).strip()
        if field:
            by_field.setdefault(field, []).append(doc)

    for field in PREFERRED_AUTO_FIELDS:
        records = by_field.get(field) or []
        if records:
            add(records[0].get("normalized_value"))
        if len(queries) >= limit:
            return queries[:limit]

    for field in PREFERRED_AUTO_FIELDS:
        if field in by_field:
            add(field)
        if len(queries) >= limit:
            return queries[:limit]

    for doc in docs:
        add(doc.get("normalized_value"))
        if len(queries) >= limit:
            break
    return queries[:limit]


def _quality_checks(summary: Mapping[str, Any], args: argparse.Namespace) -> List[Dict[str, Any]]:
    def check(name: str, observed: Any, op: str, expected: Any, passed: bool) -> Dict[str, Any]:
        return {"name": name, "observed": observed, "operator": op, "expected": expected, "passed": bool(passed)}

    return [
        check("source_exact_search_adapter_quality_pass", summary.get("source_exact_search_adapter_quality_pass"), "is True", True, (not args.require_source_exact_search_adapter_quality_pass) or bool(summary.get("source_exact_search_adapter_quality_pass"))),
        check("source_exact_search_document_count", summary.get("source_exact_search_document_count", 0), ">=", args.min_source_exact_search_documents, int(summary.get("source_exact_search_document_count", 0)) >= args.min_source_exact_search_documents),
        check("smoke_query_count", summary.get("smoke_query_count", 0), ">=", args.min_smoke_query_count, int(summary.get("smoke_query_count", 0)) >= args.min_smoke_query_count),
        check("successful_smoke_query_count", summary.get("successful_smoke_query_count", 0), ">=", args.min_successful_smoke_query_count, int(summary.get("successful_smoke_query_count", 0)) >= args.min_successful_smoke_query_count),
        check("total_match_count", summary.get("total_match_count", 0), ">=", args.min_total_match_count, int(summary.get("total_match_count", 0)) >= args.min_total_match_count),
        check("page_with_smoke_match_count", summary.get("page_with_smoke_match_count", 0), ">=", args.min_pages_with_smoke_matches, int(summary.get("page_with_smoke_match_count", 0)) >= args.min_pages_with_smoke_matches),
        check("unsafe_smoke_result_count", summary.get("unsafe_smoke_result_count", 0), "<=", args.max_unsafe_records, int(summary.get("unsafe_smoke_result_count", 0)) <= args.max_unsafe_records),
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
    results = report.get("smoke_results") or []
    lines = [
        "# TRACE-Net Table Exact-Search Smoke v1 Inspect",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        "",
        "## Smoke counters",
        f"- source_exact_search_document_count: {summary.get('source_exact_search_document_count', 0)}",
        f"- smoke_query_count: {summary.get('smoke_query_count', 0)}",
        f"- successful_smoke_query_count: {summary.get('successful_smoke_query_count', 0)}",
        f"- total_match_count: {summary.get('total_match_count', 0)}",
        f"- page_with_smoke_match_count: {summary.get('page_with_smoke_match_count', 0)}",
        "",
        "## Safety/write counters",
        f"- unsafe_smoke_result_count: {summary.get('unsafe_smoke_result_count', 0)}",
        f"- answer_permission_count: {summary.get('answer_permission_count', 0)}",
        f"- can_answer_directly_count: {summary.get('can_answer_directly_count', 0)}",
        f"- can_prove_claims_count: {summary.get('can_prove_claims_count', 0)}",
        f"- source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count', 0)}",
        f"- postgres_write_attempt_count: {summary.get('postgres_write_attempt_count', 0)}",
        f"- qdrant_write_attempt_count: {summary.get('qdrant_write_attempt_count', 0)}",
        f"- opensearch_write_attempt_count: {summary.get('opensearch_write_attempt_count', 0)}",
        f"- opensearch_upload_attempt_count: {summary.get('opensearch_upload_attempt_count', 0)}",
        "",
        "## Queries",
    ]
    if not results:
        lines.append("No smoke results generated.")
    for result in results:
        lines.append(f"- query={result.get('query')!r} matches={result.get('match_count', 0)}")
        for hit in (result.get("hits") or [])[:5]:
            lines.append(f"  - {hit.get('page_id')} | {hit.get('field_name')} | {hit.get('normalized_value')} | score={hit.get('score')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_table_exact_search_smoke(
    table_exact_search_adapter: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter, docs, source_collection = load_exact_search_documents(table_exact_search_adapter)
    source_summary = _source_summary(adapter)
    queries = list(args.query or [])
    if not queries:
        queries = derive_auto_queries(docs, args.auto_query_count)

    smoke_results: List[Dict[str, Any]] = []
    for query in queries:
        hits = search_documents(query, docs, top_k=args.top_k)
        smoke_results.append({"query": query, "match_count": len(hits), "hits": hits})

    all_hits = [hit for result in smoke_results for hit in result.get("hits", [])]
    pages = {hit.get("page_id") for hit in all_hits if hit.get("page_id")}
    field_counts = Counter(hit.get("field_name") for hit in all_hits if hit.get("field_name"))

    summary: Dict[str, Any] = {
        "source_exact_search_adapter_path": str(table_exact_search_adapter),
        "source_collection": source_collection,
        "source_exact_search_adapter_quality_pass": _source_quality_pass(adapter),
        "source_exact_search_document_count": len(docs),
        "source_table_exact_search_document_count": source_summary.get("table_exact_search_document_count", len(docs)),
        "smoke_query_count": len(smoke_results),
        "successful_smoke_query_count": sum(1 for result in smoke_results if int(result.get("match_count", 0)) > 0),
        "failed_smoke_query_count": sum(1 for result in smoke_results if int(result.get("match_count", 0)) <= 0),
        "total_match_count": len(all_hits),
        "page_with_smoke_match_count": len(pages),
        "field_count_with_smoke_match": len(field_counts),
        "field_counts": dict(sorted(field_counts.items())),
        "unsafe_smoke_result_count": 0,
        "answer_permission_count": sum(1 for hit in all_hits if _truthy(hit.get("answer_permission"))),
        "can_answer_directly_count": sum(1 for hit in all_hits if _truthy(hit.get("can_answer_directly"))),
        "can_prove_claims_count": sum(1 for hit in all_hits if _truthy(hit.get("can_prove_claims"))),
        "source_truth_mutation_allowed_count": sum(1 for hit in all_hits if _truthy(hit.get("source_truth_mutation_allowed"))),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }
    checks = _quality_checks(summary, args)
    quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL

    report_path = output_dir / REPORT_NAME
    results_jsonl_path = output_dir / RESULTS_JSONL_NAME
    inspect_md_path = output_dir / INSPECT_MD_NAME
    report: Dict[str, Any] = {
        "status": STATUS_BUILT if docs and smoke_results else STATUS_NOT_READY,
        "quality_status": quality_status,
        "summary": summary,
        "quality_checks": checks,
        "paths": {
            "report_path": str(report_path),
            "smoke_results_jsonl_path": str(results_jsonl_path),
            "inspect_md_path": str(inspect_md_path),
        },
        "smoke_results": smoke_results,
    }
    _write_json(report_path, report)
    _write_jsonl(results_jsonl_path, smoke_results)
    _write_inspect_md(inspect_md_path, report)
    return report


def add_common_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-source-exact-search-documents", type=int, default=1000)
    parser.add_argument("--min-smoke-query-count", type=int, default=3)
    parser.add_argument("--min-successful-smoke-query-count", type=int, default=3)
    parser.add_argument("--min-total-match-count", type=int, default=3)
    parser.add_argument("--min-pages-with-smoke-matches", type=int, default=1)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-exact-search-adapter-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TRACE-Net table exact-search local smoke v1.")
    parser.add_argument("--table-exact-search-adapter", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--auto-query-count", type=int, default=6)
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
    parser = argparse.ArgumentParser(description="Check TRACE-Net table exact-search smoke v1 quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    add_common_quality_args(parser)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_table_exact_search_smoke(args.table_exact_search_adapter, args.output_dir, args)
    summary = report["summary"]
    print("TRACE-Net Table Exact-Search Smoke v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in (
        "source_exact_search_document_count",
        "smoke_query_count",
        "successful_smoke_query_count",
        "failed_smoke_query_count",
        "total_match_count",
        "page_with_smoke_match_count",
        "unsafe_smoke_result_count",
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
        out_path = args.report_path.parent / QUALITY_NAME
        _write_json(out_path, quality)
    print("TRACE-Net Table Exact-Search Smoke v1 Quality")
    print(f" quality_status: {quality['quality_status']}")
    for check in quality["quality_checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f" {status} {check['name']}: observed={check['observed']} expected={check['operator']} {check['expected']}")
    return 0 if quality["quality_status"] == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
