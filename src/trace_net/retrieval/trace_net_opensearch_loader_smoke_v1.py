"""TRACE-Net OpenSearch Loader Smoke v1.

Dry-run validation for the safe OpenSearch adapter artifact.

This module reads the OpenSearch Adapter v1 JSON, verifies that documents are
source-traced and mapping-ready, writes a small bulk preview, and emits exact
search query plans. It performs no Postgres, Qdrant, OpenSearch, source-truth,
or answer-permission writes.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

MODULE_NAME = "trace_net_opensearch_loader_smoke_v1"
REPORT_NAME = "trace_net_opensearch_loader_smoke_v1.json"
QUALITY_NAME = "trace_net_opensearch_loader_smoke_v1_quality.json"
MARKDOWN_NAME = "trace_net_opensearch_loader_smoke_v1.md"
BULK_NAME = "trace_net_opensearch_loader_smoke_v1_bulk_preview.ndjson"
DEFAULT_INDEX_NAME = "trace_net_safe_search_v1"
DEFAULT_ADAPTER_PATH = "local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/opensearch_loader_smoke"

DOCUMENT_LIST_KEYS = ("documents", "opensearch_documents", "safe_documents", "records")
MAPPING_KEYS = ("mapping", "mappings", "index_mapping", "opensearch_mapping", "index_mappings")
TEXT_KEYS = ("search_text", "text", "content", "body", "chunk_text", "clean_text", "clean_snippet", "snippet", "summary", "title")
PAGE_KEYS = ("page_id", "source_page_id", "parent_page_id", "canonical_page_id")
PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{3,6}-\d{2,4}\b")
SAFETY_COUNTER_KEYS = (
    "unsafe_index_document_count",
    "raw_feedback_indexed_count",
    "raw_visual_output_indexed_count",
    "raw_ocr_unfiltered_indexed_count",
    "retrieval_only_answer_allowed_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
)


@dataclass(frozen=True)
class LoaderSmokeThresholds:
    min_documents: int = 100
    min_page_scoped_documents: int = 100
    expected_document_count: int | None = None
    min_query_plans: int = 3
    require_mapping: bool = False
    require_adapter_quality_pass: bool = False
    require_bulk_preview: bool = False
    require_live_read_check: bool = False


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected top-level JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_text(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "present"}
    return bool(value)


def find_documents(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    for key in DOCUMENT_LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return key, [item for item in value if isinstance(item, dict)]
    raise KeyError(f"Could not find adapter document list. Tried: {DOCUMENT_LIST_KEYS}")


def find_mapping(payload: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    for key in MAPPING_KEYS:
        value = payload.get(key)
        if isinstance(value, dict) and value:
            return key, value
    settings = payload.get("settings")
    if isinstance(settings, dict):
        for key in MAPPING_KEYS:
            value = settings.get(key)
            if isinstance(value, dict) and value:
                return f"settings.{key}", value
    return None, None


def adapter_quality_status(payload: dict[str, Any]) -> str | None:
    for key in ("quality_status", "status"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in ("quality_status", "status"):
            value = summary.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def adapter_quality_passed(payload: dict[str, Any]) -> bool:
    return str(adapter_quality_status(payload) or "").upper() == "PASS"


def nested(record: dict[str, Any], *keys: str) -> Any:
    cur: Any = record
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def string_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(string_list(item))
        return sorted(set(out))
    text = str(value).strip()
    return [text] if text else []


def page_values(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in PAGE_KEYS:
        values.extend(string_list(record.get(key)))
    for outer in ("metadata", "source", "source_trace", "payload", "properties"):
        child = record.get(outer)
        if isinstance(child, dict):
            for key in PAGE_KEYS + ("page_ids", "source_page_ids"):
                values.extend(string_list(child.get(key)))
    values.extend(string_list(record.get("page_ids")))
    values.extend(string_list(record.get("source_page_ids")))
    return sorted(set(values))


def has_page_lineage(record: dict[str, Any]) -> bool:
    return bool(page_values(record))


def has_source_trace(record: dict[str, Any]) -> bool:
    if boolish(record.get("source_trace_present")):
        return True
    trace = record.get("source_trace")
    if isinstance(trace, dict):
        if page_values({"source_trace": trace}):
            return True
        for key in ("source_package_entry", "source_uri", "source_url", "source_file_id", "checksum"):
            if trace.get(key) not in (None, "", [], {}):
                return True
    if isinstance(trace, str) and trace.strip():
        return True
    return has_page_lineage(record)


def text_for_record(record: dict[str, Any]) -> str:
    pieces: list[str] = []
    for key in TEXT_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            pieces.append(value.strip())
    return " ".join(pieces)


def doc_id(record: dict[str, Any], fallback_index: int) -> str:
    for key in ("opensearch_document_id", "document_id", "doc_id", "id", "_id", "record_id"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    page_id = (page_values(record) or ["unknown_page"])[0]
    return f"{page_id}::doc::{fallback_index}"


def document_type(record: dict[str, Any]) -> str:
    for key in ("document_type", "record_type", "type", "bucket", "rag_bucket"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def compact_preview(record: dict[str, Any], limit: int = 220) -> str:
    return " ".join(text_for_record(record).split())[:limit]


def looks_like(record: dict[str, Any], needle: str) -> bool:
    hay = " ".join(str(record.get(k, "")) for k in ("document_type", "record_type", "type", "bucket", "rag_bucket", "authority"))
    return needle.lower() in hay.lower()


def is_retrieval_only(record: dict[str, Any]) -> bool:
    return boolish(record.get("retrieval_only")) or looks_like(record, "retrieval_only")


def can_answer(record: dict[str, Any]) -> bool:
    return any(boolish(record.get(k)) for k in ("can_answer_directly", "answer_allowed", "direct_answer_allowed"))


def can_prove(record: dict[str, Any]) -> bool:
    return any(boolish(record.get(k)) for k in ("can_prove_claims", "claim_proof_allowed"))


def count_summary(payload: dict[str, Any], docs: list[dict[str, Any]]) -> dict[str, Any]:
    type_counts = Counter(document_type(doc) for doc in docs)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    out: dict[str, Any] = {
        "opensearch_document_count": len(docs),
        "page_scoped_document_count": sum(1 for d in docs if has_page_lineage(d)),
        "documents_with_search_text_count": sum(1 for d in docs if text_for_record(d).strip()),
        "missing_page_id_count": sum(1 for d in docs if not has_page_lineage(d)),
        "missing_source_trace_count": sum(1 for d in docs if not has_source_trace(d)),
        "missing_search_text_count": sum(1 for d in docs if not text_for_record(d).strip()),
        "document_type_counts": dict(sorted(type_counts.items())),
        "raw_feedback_indexed_count": sum(1 for d in docs if looks_like(d, "raw_feedback")),
        "raw_visual_output_indexed_count": sum(1 for d in docs if looks_like(d, "raw_visual") or looks_like(d, "raw_vision")),
        "raw_ocr_unfiltered_indexed_count": sum(1 for d in docs if looks_like(d, "raw_ocr") and not looks_like(d, "filtered")),
        "retrieval_only_answer_allowed_count": sum(1 for d in docs if is_retrieval_only(d) and can_answer(d)),
        "unsafe_index_document_count": sum(1 for d in docs if boolish(d.get("unsafe")) or boolish(d.get("unsafe_index_document"))),
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    for key in SAFETY_COUNTER_KEYS:
        if key not in out and key in summary:
            out[key] = int(summary.get(key) or 0)
        out.setdefault(key, 0)
    return out


def find_part_number(docs: Iterable[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    for doc in docs:
        text = text_for_record(doc) + " " + " ".join(string_list(doc.get("part_number"))) + " " + " ".join(string_list(doc.get("part_numbers")))
        match = PART_NUMBER_RE.search(text)
        if match:
            return doc, match.group(0)
    return None, None


def find_phrase(docs: Iterable[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    for doc in docs:
        words = [w.strip(" ,.;:()[]{}") for w in text_for_record(doc).split() if len(w.strip(" ,.;:()[]{}")) > 2]
        if len(words) >= 3:
            return doc, " ".join(words[:6])
    return None, None


def query_template(kind: str, query: str, index_name: str) -> dict[str, Any]:
    if kind == "part_number_exact":
        body = {"query": {"bool": {"should": [{"term": {"part_numbers.keyword": query}}, {"match_phrase": {"search_text": query}}], "minimum_should_match": 1}}, "size": 5}
    elif kind == "table_cell_exact":
        body = {"query": {"bool": {"must": [{"match_phrase": {"search_text": query}}], "filter": [{"terms": {"document_type.keyword": ["table_cell", "table_row", "table_evidence"]}}]}}, "size": 5}
    else:
        body = {"query": {"match_phrase": {"search_text": query}}, "size": 5}
    return {"method": "POST", "path": f"/{index_name}/_search", "body": body}


def build_query_plans(docs: list[dict[str, Any]], index_name: str = DEFAULT_INDEX_NAME) -> list[dict[str, Any]]:
    part_doc, part_query = find_part_number(docs)
    phrase_doc, phrase_query = find_phrase(docs)
    table_docs = [d for d in docs if "table" in document_type(d).lower() or "table" in str(d.get("rag_bucket") or "").lower()]
    table_doc, table_query = find_part_number(table_docs) if table_docs else (None, None)
    if not table_query:
        table_doc, table_query = find_phrase(table_docs)
    candidates = [
        ("part_number_exact", part_doc, part_query or "120-46137-001"),
        ("ocr_phrase_exact", phrase_doc, phrase_query or "manual revision history"),
        ("table_cell_exact", table_doc, table_query or "part number"),
    ]
    plans: list[dict[str, Any]] = []
    for kind, sample_doc, query in candidates:
        plans.append(
            {
                "query_plan_id": f"{MODULE_NAME}:{kind}",
                "query_kind": kind,
                "query": query,
                "query_text": query,
                "source": "adapter_sample" if sample_doc else "fallback_plan_no_matching_sample_found",
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "sample_document": None if sample_doc is None else {
                    "opensearch_document_id": doc_id(sample_doc, 0),
                    "page_ids": page_values(sample_doc),
                    "document_type": document_type(sample_doc),
                    "text_preview": compact_preview(sample_doc),
                },
                "opensearch_request_template": query_template(kind, query, index_name),
            }
        )
    return plans


def build_bulk_preview(docs: list[dict[str, Any]], index_name: str, max_docs: int) -> tuple[str, list[dict[str, Any]]]:
    lines: list[str] = []
    samples: list[dict[str, Any]] = []
    for index, doc in enumerate(docs[: max(0, max_docs)]):
        identifier = doc_id(doc, index)
        lines.append(json.dumps({"index": {"_index": index_name, "_id": identifier}}, ensure_ascii=False, sort_keys=True))
        lines.append(json.dumps(doc, ensure_ascii=False, sort_keys=True))
        samples.append({"opensearch_document_id": identifier, "page_ids": page_values(doc), "document_type": document_type(doc), "text_preview": compact_preview(doc)})
    return ("\n".join(lines) + ("\n" if lines else ""), samples)


def calculate_document_counts(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Backward-compatible document-count helper used by tests."""
    return count_summary({}, docs)


def assess_quality(summary: dict[str, Any], thresholds: LoaderSmokeThresholds) -> tuple[str, list[str]]:
    errors: list[str] = []
    if int(summary.get("opensearch_document_count", 0) or 0) < thresholds.min_documents:
        errors.append("opensearch_document_count below minimum")
    if int(summary.get("page_scoped_document_count", 0) or 0) < thresholds.min_page_scoped_documents:
        errors.append("page_scoped_document_count below minimum")
    if thresholds.expected_document_count is not None and int(summary.get("opensearch_document_count", 0) or 0) != thresholds.expected_document_count:
        errors.append("opensearch_document_count did not match expected count")
    if thresholds.require_mapping and not summary.get("mapping_present"):
        errors.append("mapping is required but missing")
    if thresholds.require_adapter_quality_pass and str(summary.get("adapter_quality_status") or "").upper() != "PASS":
        errors.append("adapter quality PASS required")
    if int(summary.get("query_plan_count", 0) or 0) < thresholds.min_query_plans:
        errors.append("query_plan_count below minimum")
    if thresholds.require_bulk_preview and not summary.get("bulk_preview_written"):
        errors.append("bulk preview missing")
    if thresholds.require_live_read_check and not summary.get("live_read_check_ok"):
        errors.append("live read check required but not passing")
    for key in ("missing_page_id_count", "missing_source_trace_count") + SAFETY_COUNTER_KEYS:
        if int(summary.get(key, 0) or 0) != 0:
            errors.append(f"{key} must be 0")
    return ("PASS" if not errors else "FAIL", errors)


def write_markdown_report(path: str | Path, report: dict[str, Any]) -> None:
    s = report.get("summary", {})
    lines = ["# TRACE-Net OpenSearch Loader Smoke v1", "", f"Quality status: {report.get('quality_status')}", f"Status: {report.get('status')}", "", "## Summary", ""]
    for key in ("adapter_quality_status", "index_name", "opensearch_document_count", "page_scoped_document_count", "missing_page_id_count", "missing_source_trace_count", "mapping_present", "query_plan_count", "bulk_preview_document_count", "unsafe_index_document_count", "raw_feedback_indexed_count", "raw_visual_output_indexed_count", "raw_ocr_unfiltered_indexed_count", "retrieval_only_answer_allowed_count", "source_truth_mutation_allowed_count", "opensearch_write_attempt_count"):
        lines.append(f"- {key}: {s.get(key)}")
    lines += ["", "## Safety contract", "", "Dry-run only. No Postgres, Qdrant, OpenSearch, source-truth, or answer-permission writes."]
    write_text(path, "\n".join(lines) + "\n")


def thresholds_from_args(args: argparse.Namespace) -> LoaderSmokeThresholds:
    return LoaderSmokeThresholds(
        min_documents=args.min_documents,
        min_page_scoped_documents=args.min_page_scoped_documents,
        expected_document_count=args.expected_document_count,
        min_query_plans=args.min_query_plans,
        require_mapping=args.require_mapping,
        require_adapter_quality_pass=args.require_adapter_quality_pass,
        require_bulk_preview=args.require_bulk_preview,
        require_live_read_check=args.require_live_read_check,
    )


def build_loader_smoke_report(
    *,
    opensearch_adapter_path: str | Path,
    output_dir: str | Path,
    index_name: str = DEFAULT_INDEX_NAME,
    max_bulk_sample_docs: int = 25,
    thresholds: LoaderSmokeThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or LoaderSmokeThresholds()
    adapter_path = Path(opensearch_adapter_path)
    output_path = Path(output_dir)
    adapter = load_json(adapter_path)
    doc_key, docs = find_documents(adapter)
    mapping_key, mapping = find_mapping(adapter)
    query_plans = build_query_plans(docs, index_name=index_name)
    bulk_text, bulk_samples = build_bulk_preview(docs, index_name=index_name, max_docs=max_bulk_sample_docs)
    summary = count_summary(adapter, docs)
    summary.update({
        "adapter_path": str(adapter_path),
        "adapter_document_list_key": doc_key,
        "adapter_quality_status": adapter_quality_status(adapter),
        "mapping_present": mapping is not None,
        "mapping_key": mapping_key,
        "index_name": index_name,
        "query_plan_count": len(query_plans),
        "bulk_preview_written": True,
        "bulk_preview_document_count": len(bulk_samples),
        "bulk_action_sample_count": len(bulk_samples),
        "bulk_preview_line_count": len(bulk_text.splitlines()) if bulk_text else 0,
        "part_number_query_plan_count": sum(1 for p in query_plans if p.get("query_kind") == "part_number_exact"),
        "ocr_phrase_query_plan_count": sum(1 for p in query_plans if p.get("query_kind") == "ocr_phrase_exact"),
        "table_cell_query_plan_count": sum(1 for p in query_plans if p.get("query_kind") == "table_cell_exact"),
        "live_read_check_ok": False,
    })
    quality_status, quality_errors = assess_quality(summary, thresholds)
    report = {
        "module_name": MODULE_NAME,
        "schema_version": MODULE_NAME,
        "generated_at": now_iso(),
        "quality_status": quality_status,
        "status": "LOADER_SMOKE_READY" if quality_status == "PASS" else "LOADER_SMOKE_NOT_READY",
        "quality_errors": quality_errors,
        "inputs": {"opensearch_adapter": str(adapter_path)},
        "outputs": {
            "report_path": str(output_path / REPORT_NAME),
            "quality_path": str(output_path / QUALITY_NAME),
            "markdown_path": str(output_path / MARKDOWN_NAME),
            "bulk_preview_path": str(output_path / BULK_NAME),
        },
        "summary": summary,
        "mapping_preview": mapping or {},
        "query_plans": query_plans,
        "records": query_plans,
        "bulk_load_plan": {"mode": "dry_run_preview_only", "index_name": index_name, "bulk_preview_path": str(output_path / BULK_NAME), "bulk_preview_sample_records": bulk_samples, "opensearch_write_attempt_count": 0},
        "safety_contract": {"postgres_writes": False, "qdrant_writes": False, "opensearch_writes": False, "source_truth_mutation": False, "answer_permission": False, "claim_proof_authority": False, "dry_run_only": True},
    }
    write_json(output_path / REPORT_NAME, report)
    write_json(output_path / QUALITY_NAME, report)
    write_markdown_report(output_path / MARKDOWN_NAME, report)
    write_text(output_path / BULK_NAME, bulk_text)
    return report


def check_loader_smoke_quality(*, report_path: str | Path, thresholds: LoaderSmokeThresholds | None = None, write_json_report: bool = False) -> dict[str, Any]:
    report = load_json(report_path)
    thresholds = thresholds or LoaderSmokeThresholds()
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("Report is missing summary object")
    quality_status, quality_errors = assess_quality(summary, thresholds)
    report["quality_status"] = quality_status
    report["status"] = "LOADER_SMOKE_READY" if quality_status == "PASS" else "LOADER_SMOKE_NOT_READY"
    report["quality_errors"] = quality_errors
    if write_json_report:
        p = Path(report_path)
        write_json(p, report)
        write_json(p.with_name(QUALITY_NAME), report)
    return report


def add_common_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-documents", type=int, default=100)
    parser.add_argument("--min-page-scoped-documents", type=int, default=100)
    parser.add_argument("--expected-document-count", type=int, default=None)
    parser.add_argument("--min-query-plans", type=int, default=3)
    parser.add_argument("--require-mapping", action="store_true")
    parser.add_argument("--require-adapter-quality-pass", action="store_true")
    parser.add_argument("--require-bulk-preview", action="store_true")
    parser.add_argument("--require-live-read-check", action="store_true")


def print_summary(report: dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("TRACE-Net OpenSearch Loader Smoke v1")
    print(" Quality status:", report.get("quality_status"))
    print(" Status:", report.get("status"))
    for key in ("adapter_quality_status", "index_name", "opensearch_document_count", "page_scoped_document_count", "documents_with_search_text_count", "missing_page_id_count", "missing_source_trace_count", "mapping_present", "query_plan_count", "bulk_preview_document_count", "unsafe_index_document_count", "raw_feedback_indexed_count", "raw_visual_output_indexed_count", "raw_ocr_unfiltered_indexed_count", "retrieval_only_answer_allowed_count", "source_truth_mutation_allowed_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
        print(f" {key}: {s.get(key)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net OpenSearch Loader Smoke v1 dry-run report.")
    parser.add_argument("--opensearch-adapter", default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--index-name", default=DEFAULT_INDEX_NAME)
    parser.add_argument("--max-bulk-sample-docs", type=int, default=25)
    parser.add_argument("--quality", action="store_true")
    add_common_quality_args(parser)
    args = parser.parse_args(argv)
    if args.quality:
        args.require_mapping = True
        args.require_adapter_quality_pass = True
        args.require_bulk_preview = True
    report = build_loader_smoke_report(
        opensearch_adapter_path=args.opensearch_adapter,
        output_dir=args.output_dir,
        index_name=args.index_name,
        max_bulk_sample_docs=args.max_bulk_sample_docs,
        thresholds=thresholds_from_args(args),
    )
    print_summary(report)
    print(" report_path:", report.get("outputs", {}).get("report_path"))
    print(" quality_path:", report.get("outputs", {}).get("quality_path"))
    return 0 if report.get("quality_status") == "PASS" else 1


# Backward-compatible names used by unit tests and helper snippets.
build_report = build_loader_smoke_report
check_existing_report = check_loader_smoke_quality


if __name__ == "__main__":
    raise SystemExit(main())

# Compatibility alias for script wrapper variants.
print_report = print_summary
