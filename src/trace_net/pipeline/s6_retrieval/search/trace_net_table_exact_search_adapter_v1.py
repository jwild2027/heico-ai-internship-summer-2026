"""TRACE-Net table exact-search adapter v1.

Builds local-only exact-search documents from table-route evidence-package
records. This module intentionally does not upload to OpenSearch and never grants
answer authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

STATUS_BUILT = "TABLE_EXACT_SEARCH_ADAPTER_BUILT"
STATUS_NOT_READY = "TABLE_EXACT_SEARCH_ADAPTER_NOT_READY"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

REPORT_NAME = "trace_net_table_exact_search_adapter_v1.json"
QUALITY_NAME = "trace_net_table_exact_search_adapter_v1_quality.json"
DOCS_JSONL_NAME = "trace_net_table_exact_search_documents_v1.jsonl"
BULK_NDJSON_NAME = "trace_net_table_exact_search_bulk_v1.ndjson"
MAPPING_NAME = "trace_net_table_exact_search_mapping_v1.json"
INSPECT_MD_NAME = "trace_net_table_exact_search_adapter_v1_inspect.md"
DEFAULT_INDEX_NAME = "trace-net-table-route-evidence-v1"

FALSE_VALUES = {False, 0, "0", "false", "False", "FALSE", "no", "No", "NO", ""}
TRUE_VALUES = {True, 1, "1", "true", "True", "TRUE", "yes", "Yes", "YES"}

FIELD_ALIASES = (
    "field_name",
    "field",
    "field_role",
    "normalized_field_name",
    "evidence_field",
    "role",
)
VALUE_ALIASES = (
    "normalized_value",
    "value",
    "evidence_value",
    "display_value",
    "text_value",
    "normalized_text",
    "raw_value",
    "cell_text",
    "text",
)
RAW_VALUE_ALIASES = (
    "raw_value",
    "cell_text",
    "text",
    "ocr_text",
    "display_value",
    "normalized_value",
    "value",
)

BLOCK_FLAGS = (
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
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "review_only",
    "context_only",
    "suppressed",
    "skipped",
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
            rows.append(json.loads(line))
    return rows


def _truthy(value: Any) -> bool:
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES or value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    return bool(value)


def _first_nonempty(mapping: Mapping[str, Any], aliases: Sequence[str]) -> str:
    for key in aliases:
        value = mapping.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _safe_id_text(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value.strip())[:160] or "unknown"


def _stable_hash(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:16]


def _tokenize_for_exact_search(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.\-/]*", text or "")
    seen = set()
    out: List[str] = []
    for token in tokens:
        low = token.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(token)
    return out[:64]


def _source_quality_pass(package: Mapping[str, Any]) -> bool:
    status = str(package.get("quality_status", package.get("summary", {}).get("quality_status", ""))).upper()
    if status == QUALITY_PASS:
        return True
    summary = package.get("summary") or {}
    return bool(summary.get("quality_status") == QUALITY_PASS or summary.get("source_quality_pass") is True)


def _source_summary(package: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = package.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _find_evidence_jsonl_path(package: Mapping[str, Any], report_path: Path) -> Optional[Path]:
    candidates: List[Any] = [
        package.get("evidence_jsonl_path"),
        package.get("evidence_documents_jsonl_path"),
        package.get("table_route_evidence_documents_jsonl_path"),
    ]
    paths = package.get("paths")
    if isinstance(paths, Mapping):
        candidates.extend(
            [
                paths.get("evidence_jsonl_path"),
                paths.get("evidence_documents_jsonl_path"),
                paths.get("table_route_evidence_documents_jsonl_path"),
            ]
        )
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate))
        if not path.is_absolute():
            # Prefer paths relative to the repository root/current working dir, then report parent.
            if path.exists():
                return path
            alt = report_path.parent / path.name
            if alt.exists():
                return alt
        elif path.exists():
            return path
    sibling = report_path.parent / "trace_net_table_route_evidence_documents_v1.jsonl"
    if sibling.exists():
        return sibling
    return None


def load_evidence_documents(package_path: Path) -> Tuple[Mapping[str, Any], List[Dict[str, Any]], str]:
    package = _read_json(package_path)
    if not isinstance(package, Mapping):
        raise ValueError(f"Expected JSON object at {package_path}")

    for key in (
        "evidence_documents",
        "table_route_evidence_documents",
        "table_route_evidence_document_records",
        "documents",
        "records",
    ):
        value = package.get(key)
        if isinstance(value, list):
            return package, [dict(row) for row in value if isinstance(row, Mapping)], key

    jsonl_path = _find_evidence_jsonl_path(package, package_path)
    if jsonl_path is not None:
        return package, _read_jsonl(jsonl_path), str(jsonl_path)

    return package, [], "none"


def _is_blocked_source_record(record: Mapping[str, Any]) -> bool:
    for key in BLOCK_FLAGS:
        if _truthy(record.get(key)):
            return True
    status = str(record.get("quality_status", "")).upper()
    if status and status not in {QUALITY_PASS, "OK", "READY"}:
        return True
    permission = str(record.get("answer_permission_status", "")).lower()
    if permission and permission not in {"none", "false", "retrieval_only", "not_allowed"}:
        return True
    return False


def _make_source_trace(record: Mapping[str, Any]) -> Dict[str, Any]:
    trace = record.get("source_trace")
    if isinstance(trace, Mapping):
        out = dict(trace)
    else:
        out = {}
    for key in ("page_id", "source_page_id", "document_id", "source_package_id", "table_id", "row_id", "cell_id"):
        value = record.get(key)
        if value is not None and str(value).strip() and key not in out:
            out[key] = value
    return out


def make_exact_search_document(record: Mapping[str, Any], index: int) -> Optional[Dict[str, Any]]:
    if _is_blocked_source_record(record):
        return None

    field_name = _first_nonempty(record, FIELD_ALIASES)
    normalized_value = _first_nonempty(record, VALUE_ALIASES)
    raw_value = _first_nonempty(record, RAW_VALUE_ALIASES) or normalized_value
    if not field_name or not normalized_value:
        return None

    page_id = _first_nonempty(record, ("page_id", "source_page_id", "page", "page_key"))
    table_id = _first_nonempty(record, ("table_id", "source_table_id", "table_key"))
    source_evidence_id = _first_nonempty(record, ("evidence_id", "document_id", "record_id", "value_id", "cell_id"))
    template = _first_nonempty(record, ("template_name", "table_template", "template", "detected_template"))

    id_basis = {
        "source_evidence_id": source_evidence_id,
        "page_id": page_id,
        "table_id": table_id,
        "field_name": field_name,
        "normalized_value": normalized_value,
        "row_id": record.get("row_id"),
        "cell_id": record.get("cell_id"),
        "index": index,
    }
    stable = _stable_hash(id_basis)
    doc_id = f"table_exact_search::{_safe_id_text(page_id or 'page')}::{_safe_id_text(field_name)}::{stable}"

    search_text_parts = [
        "TRACE-Net table evidence",
        str(page_id),
        str(table_id),
        str(template),
        str(field_name),
        str(normalized_value),
        str(raw_value),
        str(record.get("context_text", "")),
    ]
    search_text = " | ".join(part for part in search_text_parts if part and part != "None")

    return {
        "document_id": doc_id,
        "record_type": "table_route_exact_search_document",
        "search_family": "table_route_exact_search",
        "route": "table",
        "source_evidence_id": source_evidence_id,
        "page_id": page_id,
        "source_page_id": record.get("source_page_id") or page_id,
        "table_id": table_id,
        "row_id": record.get("row_id", ""),
        "cell_id": record.get("cell_id", ""),
        "field_name": field_name,
        "field_role": record.get("field_role") or field_name,
        "normalized_value": normalized_value,
        "raw_value": raw_value,
        "display_value": record.get("display_value") or normalized_value,
        "table_template": template,
        "confidence": record.get("confidence", record.get("evidence_confidence", "")),
        "search_text": search_text,
        "search_tokens": _tokenize_for_exact_search(search_text),
        "source_trace": _make_source_trace(record),
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


def make_opensearch_mapping(index_name: str = DEFAULT_INDEX_NAME) -> Dict[str, Any]:
    keyword_fields = [
        "document_id",
        "record_type",
        "search_family",
        "route",
        "source_evidence_id",
        "page_id",
        "source_page_id",
        "table_id",
        "row_id",
        "cell_id",
        "field_name",
        "field_role",
        "table_template",
    ]
    properties: Dict[str, Any] = {
        field: {"type": "keyword"} for field in keyword_fields
    }
    properties.update(
        {
            "normalized_value": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}},
            "raw_value": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}},
            "display_value": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}},
            "search_text": {"type": "text"},
            "search_tokens": {"type": "keyword"},
            "source_trace": {"type": "object", "enabled": True},
            "retrieval_only": {"type": "boolean"},
            "answer_permission": {"type": "boolean"},
            "can_answer_directly": {"type": "boolean"},
            "can_prove_claims": {"type": "boolean"},
            "source_truth_mutation_allowed": {"type": "boolean"},
            "unsafe": {"type": "boolean"},
            "postgres_write_attempted": {"type": "boolean"},
            "qdrant_write_attempted": {"type": "boolean"},
            "opensearch_write_attempted": {"type": "boolean"},
            "opensearch_upload_attempted": {"type": "boolean"},
        }
    )
    return {
        "index_name": index_name,
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {"dynamic": "strict", "properties": properties},
    }


def build_bulk_lines(documents: Sequence[Mapping[str, Any]], index_name: str = DEFAULT_INDEX_NAME) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    for doc in documents:
        lines.append({"index": {"_index": index_name, "_id": doc["document_id"]}})
        lines.append(dict(doc))
    return lines


def _quality_checks(summary: Mapping[str, Any], args: argparse.Namespace) -> List[Dict[str, Any]]:
    def check(name: str, observed: Any, op: str, expected: Any, passed: bool) -> Dict[str, Any]:
        return {"name": name, "observed": observed, "operator": op, "expected": expected, "passed": bool(passed)}

    field_counts = summary.get("field_counts") or {}
    return [
        check("source_evidence_package_quality_pass", summary.get("source_evidence_package_quality_pass"), "is True", True, (not args.require_source_evidence_package_quality_pass) or bool(summary.get("source_evidence_package_quality_pass"))),
        check("source_evidence_document_count", summary.get("source_evidence_document_count", 0), ">=", args.min_source_evidence_documents, int(summary.get("source_evidence_document_count", 0)) >= args.min_source_evidence_documents),
        check("table_exact_search_document_count", summary.get("table_exact_search_document_count", 0), ">=", args.min_exact_search_documents, int(summary.get("table_exact_search_document_count", 0)) >= args.min_exact_search_documents),
        check("page_with_exact_search_document_count", summary.get("page_with_exact_search_document_count", 0), ">=", args.min_pages_with_exact_search_documents, int(summary.get("page_with_exact_search_document_count", 0)) >= args.min_pages_with_exact_search_documents),
        check("field_count", summary.get("field_count", 0), ">=", args.min_field_count, int(summary.get("field_count", 0)) >= args.min_field_count),
        check("covered_part_number_documents", field_counts.get("covered_part_number", 0), ">=", args.min_covered_part_number_documents, int(field_counts.get("covered_part_number", 0)) >= args.min_covered_part_number_documents),
        check("manual_page_reference_documents", field_counts.get("manual_page_reference", 0), ">=", args.min_manual_page_reference_documents, int(field_counts.get("manual_page_reference", 0)) >= args.min_manual_page_reference_documents),
        check("ipl_part_number_documents", field_counts.get("ipl_part_number", 0), ">=", args.min_ipl_part_number_documents, int(field_counts.get("ipl_part_number", 0)) >= args.min_ipl_part_number_documents),
        check("unsafe_exact_search_document_count", summary.get("unsafe_exact_search_document_count", 0), "<=", args.max_unsafe_records, int(summary.get("unsafe_exact_search_document_count", 0)) <= args.max_unsafe_records),
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
    docs = report.get("exact_search_documents") or []
    lines = [
        "# TRACE-Net Table Exact-Search Adapter v1 Inspect",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        "",
        "## Adapter counters",
        f"- source_evidence_document_count: {summary.get('source_evidence_document_count', 0)}",
        f"- table_exact_search_document_count: {summary.get('table_exact_search_document_count', 0)}",
        f"- page_with_exact_search_document_count: {summary.get('page_with_exact_search_document_count', 0)}",
        f"- table_with_exact_search_document_count: {summary.get('table_with_exact_search_document_count', 0)}",
        f"- field_count: {summary.get('field_count', 0)}",
        "",
        "## Field counts",
    ]
    if field_counts:
        for key, value in sorted(field_counts.items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Safety/write counters",
            f"- unsafe_exact_search_document_count: {summary.get('unsafe_exact_search_document_count', 0)}",
            f"- answer_permission_count: {summary.get('answer_permission_count', 0)}",
            f"- can_answer_directly_count: {summary.get('can_answer_directly_count', 0)}",
            f"- can_prove_claims_count: {summary.get('can_prove_claims_count', 0)}",
            f"- source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count', 0)}",
            f"- postgres_write_attempt_count: {summary.get('postgres_write_attempt_count', 0)}",
            f"- qdrant_write_attempt_count: {summary.get('qdrant_write_attempt_count', 0)}",
            f"- opensearch_write_attempt_count: {summary.get('opensearch_write_attempt_count', 0)}",
            f"- opensearch_upload_attempt_count: {summary.get('opensearch_upload_attempt_count', 0)}",
            "",
            "## First exact-search documents",
        ]
    )
    if docs:
        for doc in docs[:20]:
            lines.append(f"- {doc.get('page_id')} | {doc.get('field_name')} | {doc.get('normalized_value')}")
    else:
        lines.append("No exact-search documents packaged.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_table_exact_search_adapter(
    table_route_evidence_packager: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    package, evidence_records, source_collection = load_evidence_documents(table_route_evidence_packager)
    source_summary = _source_summary(package)

    exact_docs: List[Dict[str, Any]] = []
    for idx, record in enumerate(evidence_records):
        doc = make_exact_search_document(record, idx)
        if doc is not None:
            exact_docs.append(doc)

    field_counts = Counter(doc["field_name"] for doc in exact_docs)
    pages = {doc.get("page_id") for doc in exact_docs if doc.get("page_id")}
    tables = {doc.get("table_id") for doc in exact_docs if doc.get("table_id")}

    summary: Dict[str, Any] = {
        "source_evidence_package_path": str(table_route_evidence_packager),
        "source_collection": source_collection,
        "source_evidence_package_quality_pass": _source_quality_pass(package),
        "source_evidence_document_count": len(evidence_records),
        "source_table_route_evidence_document_count": source_summary.get("table_route_evidence_document_count", len(evidence_records)),
        "table_exact_search_document_count": len(exact_docs),
        "page_with_exact_search_document_count": len(pages),
        "table_with_exact_search_document_count": len(tables),
        "field_count": len(field_counts),
        "field_counts": dict(sorted(field_counts.items())),
        "unsafe_exact_search_document_count": sum(1 for doc in exact_docs if _truthy(doc.get("unsafe"))),
        "answer_permission_count": sum(1 for doc in exact_docs if _truthy(doc.get("answer_permission"))),
        "can_answer_directly_count": sum(1 for doc in exact_docs if _truthy(doc.get("can_answer_directly"))),
        "can_prove_claims_count": sum(1 for doc in exact_docs if _truthy(doc.get("can_prove_claims"))),
        "source_truth_mutation_allowed_count": sum(1 for doc in exact_docs if _truthy(doc.get("source_truth_mutation_allowed"))),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "retrieval_only_document_count": sum(1 for doc in exact_docs if _truthy(doc.get("retrieval_only"))),
    }

    checks = _quality_checks(summary, args)
    quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL

    docs_jsonl_path = output_dir / DOCS_JSONL_NAME
    bulk_path = output_dir / BULK_NDJSON_NAME
    mapping_path = output_dir / MAPPING_NAME
    report_path = output_dir / REPORT_NAME
    inspect_md_path = output_dir / INSPECT_MD_NAME

    mapping = make_opensearch_mapping(args.index_name)
    bulk_lines = build_bulk_lines(exact_docs, args.index_name)
    _write_jsonl(docs_jsonl_path, exact_docs)
    _write_jsonl(bulk_path, bulk_lines)
    _write_json(mapping_path, mapping)

    report: Dict[str, Any] = {
        "status": STATUS_BUILT if exact_docs else STATUS_NOT_READY,
        "quality_status": quality_status,
        "summary": summary,
        "quality_checks": checks,
        "paths": {
            "report_path": str(report_path),
            "exact_search_jsonl_path": str(docs_jsonl_path),
            "opensearch_bulk_ndjson_path": str(bulk_path),
            "opensearch_mapping_path": str(mapping_path),
            "inspect_md_path": str(inspect_md_path),
        },
        "index_name": args.index_name,
        "exact_search_documents": exact_docs,
    }
    _write_json(report_path, report)
    _write_inspect_md(inspect_md_path, report)
    return report


def add_common_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-source-evidence-documents", type=int, default=1000)
    parser.add_argument("--min-exact-search-documents", type=int, default=1000)
    parser.add_argument("--min-pages-with-exact-search-documents", type=int, default=1)
    parser.add_argument("--min-field-count", type=int, default=4)
    parser.add_argument("--min-covered-part-number-documents", type=int, default=100)
    parser.add_argument("--min-manual-page-reference-documents", type=int, default=39)
    parser.add_argument("--min-ipl-part-number-documents", type=int, default=100)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-evidence-package-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table exact-search adapter v1 artifacts.")
    parser.add_argument("--table-route-evidence-packager", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--index-name", default=DEFAULT_INDEX_NAME)
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
    parser = argparse.ArgumentParser(description="Check TRACE-Net table exact-search adapter v1 quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    add_common_quality_args(parser)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_table_exact_search_adapter(args.table_route_evidence_packager, args.output_dir, args)
    summary = report["summary"]
    print("TRACE-Net Table Exact-Search Adapter v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in (
        "source_evidence_document_count",
        "table_exact_search_document_count",
        "page_with_exact_search_document_count",
        "table_with_exact_search_document_count",
        "field_count",
        "unsafe_exact_search_document_count",
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
    print("TRACE-Net Table Exact-Search Adapter v1 Quality")
    print(f" quality_status: {quality['quality_status']}")
    for check in quality["quality_checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f" {status} {check['name']}: observed={check['observed']} expected={check['operator']} {check['expected']}")
    return 0 if quality["quality_status"] == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
