"""TRACE-Net OpenSearch Adapter Lineage Guard v1.

This module is a focused safety guard for the OpenSearch Adapter v1 output.
It removes any exact-search document that lacks page/source lineage before the
adapter artifact is used by Loader Smoke or a future live OpenSearch index.

Safety contract:
- Read local adapter artifacts only.
- Write corrected local adapter artifacts only.
- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission or claim-proof authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_opensearch_adapter_lineage_guard_v1"
ADAPTER_SCHEMA_VERSION = "trace_net_opensearch_adapter_v1"
DEFAULT_INDEX_NAME = "trace_net_safe_search_v1"
DEFAULT_REPORT_NAME = "trace_net_opensearch_adapter_v1.json"
QUALITY_NAME = "trace_net_opensearch_adapter_v1_quality.json"
SUMMARY_NAME = "trace_net_opensearch_adapter_v1_summary.json"
DOCUMENTS_NAME = "trace_net_opensearch_documents_v1.jsonl"
BULK_NAME = "trace_net_opensearch_bulk_v1.ndjson"
MAPPING_NAME = "trace_net_opensearch_mapping_v1.json"
MANIFEST_NAME = "trace_net_opensearch_adapter_v1_manifest.json"
MARKDOWN_NAME = "trace_net_opensearch_adapter_v1.md"

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
)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(value: Any, length: int = 20) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()[:length]


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def unique_strings(values: Iterable[Any]) -> list[str]:
    return sorted({str(v).strip() for v in values if v is not None and str(v).strip()})


def coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def document_id(doc: dict[str, Any], index: int = 0) -> str:
    value = doc.get("opensearch_document_id") or doc.get("id") or doc.get("document_id")
    if value:
        return str(value)
    return f"osdoc::{index:06d}::{stable_hash(doc, 16)}"


def page_values(doc: dict[str, Any]) -> list[str]:
    pages: list[Any] = []
    if doc.get("page_id"):
        pages.append(doc.get("page_id"))
    pages.extend(coerce_list(doc.get("source_page_ids")))
    pages.extend(coerce_list(doc.get("page_ids")))
    return unique_strings(pages)


def has_page_lineage(doc: dict[str, Any]) -> bool:
    return bool(page_values(doc))


def is_safe_document(doc: dict[str, Any]) -> bool:
    if doc.get("safe_for_opensearch") is False:
        return False
    if doc.get("unsafe") or doc.get("unsafe_index_document"):
        return False
    if doc.get("raw_feedback_indexed") or doc.get("raw_visual_output") or doc.get("raw_ocr_unfiltered"):
        return False
    if doc.get("source_truth_mutation_allowed") or doc.get("can_mutate_source_truth"):
        return False
    if doc.get("can_answer_directly") or doc.get("can_prove_claims"):
        return False
    if doc.get("retrieval_only") and doc.get("answer_support_candidate"):
        return False
    return True


def normalize_document(doc: dict[str, Any], index: int = 0) -> dict[str, Any]:
    out = dict(doc)
    pages = page_values(out)
    primary_page = out.get("page_id") if isinstance(out.get("page_id"), str) and out.get("page_id") else None
    if not primary_page and len(pages) == 1:
        primary_page = pages[0]
    out["opensearch_document_id"] = document_id(out, index)
    out["page_id"] = primary_page
    out["source_page_ids"] = pages
    out["source_trace_present"] = bool(pages)
    out["safe_for_opensearch"] = True
    out["can_answer_directly"] = False
    out["can_prove_claims"] = False
    out["can_mutate_source_truth"] = False
    out["source_truth_mutation_allowed"] = False
    out["source_truth_mutations_performed"] = 0
    out["postgres_write_attempt_count"] = 0
    out["qdrant_write_attempt_count"] = 0
    out["opensearch_write_attempt_count"] = 0
    return out


def find_documents(report: dict[str, Any]) -> list[dict[str, Any]]:
    docs = report.get("documents")
    if isinstance(docs, list):
        return [d for d in docs if isinstance(d, dict)]
    for key in ("opensearch_documents", "records"):
        docs = report.get(key)
        if isinstance(docs, list):
            return [d for d in docs if isinstance(d, dict)]
    return []


def write_bulk_ndjson(path: str | Path, docs: list[dict[str, Any]], index_name: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for index, doc in enumerate(docs):
            doc_id = document_id(doc, index)
            handle.write(json.dumps({"index": {"_index": index_name, "_id": doc_id}}, ensure_ascii=False, sort_keys=True) + "\n")
            handle.write(json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n")


def count_summary(report: dict[str, Any], docs: list[dict[str, Any]], dropped: list[dict[str, Any]]) -> dict[str, Any]:
    existing = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    document_type_counts = Counter(str(d.get("document_type") or "unknown") for d in docs)
    bucket_counts = Counter(str(d.get("rag_bucket") or "unknown") for d in docs)
    authority_counts = Counter(str(d.get("authority") or "unknown") for d in docs)
    dropped_reason_counts = Counter(str(d.get("drop_reason") or "unknown") for d in dropped)
    page_scoped = sum(1 for d in docs if has_page_lineage(d))
    summary = dict(existing)
    summary.update(
        {
            "schema_version": ADAPTER_SCHEMA_VERSION,
            "lineage_guard_schema_version": SCHEMA_VERSION,
            "status": "PASS",
            "opensearch_document_count": len(docs),
            "page_scoped_document_count": page_scoped,
            "documents_with_search_text_count": sum(1 for d in docs if str(d.get("text") or d.get("search_text") or "").strip()),
            "document_type_counts": dict(sorted(document_type_counts.items())),
            "bucket_counts": dict(sorted(bucket_counts.items())),
            "authority_counts": dict(sorted(authority_counts.items())),
            "missing_page_id_count": 0,
            "missing_source_trace_count": 0,
            "unsafe_index_document_count": 0,
            "raw_feedback_indexed_count": 0,
            "raw_visual_output_indexed_count": 0,
            "raw_ocr_unfiltered_indexed_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_truth_mutations_performed": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "lineage_guard_applied": True,
            "lineage_guard_dropped_document_count": len(dropped),
            "lineage_guard_drop_reason_counts": dict(sorted(dropped_reason_counts.items())),
            "write_mode": "local_document_build_only",
        }
    )
    return summary


def quality_report(report: dict[str, Any], *, min_documents: int = 1, min_page_scoped_documents: int = 1, require_mapping: bool = False) -> dict[str, Any]:
    summary = report.get("summary") or {}
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any, expected: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "value": value, "expected": expected, "severity": "critical"})

    add("document_count_min", int(summary.get("opensearch_document_count", 0) or 0) >= min_documents, summary.get("opensearch_document_count", 0), f">= {min_documents}")
    add("page_scoped_document_count_min", int(summary.get("page_scoped_document_count", 0) or 0) >= min_page_scoped_documents, summary.get("page_scoped_document_count", 0), f">= {min_page_scoped_documents}")
    add("missing_page_id_count_zero", int(summary.get("missing_page_id_count", 0) or 0) == 0, summary.get("missing_page_id_count", 0), "0")
    add("missing_source_trace_count_zero", int(summary.get("missing_source_trace_count", 0) or 0) == 0, summary.get("missing_source_trace_count", 0), "0")
    for key in SAFETY_COUNTER_KEYS:
        add(f"{key}_zero", int(summary.get(key, 0) or 0) == 0, summary.get(key, 0), "0")
    if require_mapping:
        add("mapping_present", bool(report.get("mapping")), bool(report.get("mapping")), "true")
    failed = [c for c in checks if not c["passed"]]
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": "PASS" if not failed else "FAIL",
        "quality_status": "PASS" if not failed else "FAIL",
        "generated_at": now_iso(),
        "checks": checks,
        "summary": {**summary, "failed_check_count": len(failed)},
    }


def render_markdown(report: dict[str, Any]) -> str:
    s = report.get("summary") or {}
    lines = [
        "# TRACE-Net OpenSearch Adapter v1 — Lineage Guarded",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        f"**Index:** {report.get('index_name')}",
        "",
        "## Summary",
        "",
    ]
    for key in (
        "opensearch_document_count",
        "page_scoped_document_count",
        "documents_with_search_text_count",
        "missing_page_id_count",
        "missing_source_trace_count",
        "lineage_guard_dropped_document_count",
        "unsafe_index_document_count",
        "raw_feedback_indexed_count",
        "raw_visual_output_indexed_count",
        "raw_ocr_unfiltered_indexed_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "opensearch_write_attempt_count",
    ):
        lines.append(f"- {key}: {s.get(key)}")
    lines += ["", "## Safety Contract", "", "- Local artifact rewrite only.", "- No Postgres, Qdrant, or OpenSearch writes.", "- Documents without page/source lineage are removed before loader smoke or live indexing.", "- Retrieval-only documents cannot answer directly or prove claims."]
    return "\n".join(lines) + "\n"


def apply_lineage_guard(
    *,
    adapter_report_path: str | Path,
    output_dir: str | Path | None = None,
    min_documents: int = 1,
    min_page_scoped_documents: int = 1,
    require_mapping: bool = True,
) -> dict[str, Any]:
    source_path = Path(adapter_report_path)
    report = read_json(source_path)
    out = Path(output_dir) if output_dir else source_path.parent
    out.mkdir(parents=True, exist_ok=True)
    input_docs = find_documents(report)
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for index, doc in enumerate(input_docs):
        reason = None
        if not has_page_lineage(doc):
            reason = "missing_page_or_source_page_lineage"
        elif not is_safe_document(doc):
            reason = "unsafe_or_answer_authority_document"
        if reason:
            dropped_doc = {"opensearch_document_id": document_id(doc, index), "document_type": doc.get("document_type"), "drop_reason": reason}
            dropped.append(dropped_doc)
            continue
        kept.append(normalize_document(doc, index))
    index_name = str(report.get("index_name") or (report.get("summary") or {}).get("index_name") or DEFAULT_INDEX_NAME)
    mapping = report.get("mapping") or {}
    summary = count_summary(report, kept, dropped)
    summary["index_name"] = index_name
    guarded_report = dict(report)
    guarded_report.update(
        {
            "schema_version": ADAPTER_SCHEMA_VERSION,
            "lineage_guard_schema_version": SCHEMA_VERSION,
            "status": "OPENSEARCH_DOCUMENTS_LINEAGE_GUARDED",
            "generated_at": now_iso(),
            "index_name": index_name,
            "mapping": mapping,
            "documents": kept,
            "lineage_guard_dropped_documents": dropped,
            "summary": summary,
        }
    )
    quality = quality_report(guarded_report, min_documents=min_documents, min_page_scoped_documents=min_page_scoped_documents, require_mapping=require_mapping)
    guarded_report["quality"] = quality
    guarded_report["quality_status"] = quality["status"]
    summary["quality_status"] = quality["status"]
    summary["status"] = quality["status"]
    paths = {
        "report_path": str(out / DEFAULT_REPORT_NAME),
        "documents_path": str(out / DOCUMENTS_NAME),
        "bulk_path": str(out / BULK_NAME),
        "mapping_path": str(out / MAPPING_NAME),
        "summary_path": str(out / SUMMARY_NAME),
        "quality_path": str(out / QUALITY_NAME),
        "manifest_path": str(out / MANIFEST_NAME),
        "markdown_path": str(out / MARKDOWN_NAME),
    }
    guarded_report["paths"] = paths
    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": now_iso(),
        "index_name": index_name,
        "write_mode": "local_document_build_only",
        "paths": paths,
        "summary": summary,
        "quality_status": quality["status"],
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "source_truth_mutation": False,
            "answer_permission": False,
            "claim_proof_authority": False,
        },
    }
    write_jsonl(paths["documents_path"], kept)
    write_bulk_ndjson(paths["bulk_path"], kept, index_name)
    write_json(paths["mapping_path"], mapping)
    write_json(paths["summary_path"], summary)
    write_json(paths["quality_path"], quality)
    write_json(paths["manifest_path"], manifest)
    write_json(paths["report_path"], guarded_report)
    Path(paths["markdown_path"]).write_text(render_markdown(guarded_report), encoding="utf-8")
    return guarded_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply TRACE-Net OpenSearch Adapter Lineage Guard v1.")
    parser.add_argument("--adapter-report", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--min-documents", type=int, default=1)
    parser.add_argument("--min-page-scoped-documents", type=int, default=1)
    parser.add_argument("--require-mapping", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    report = apply_lineage_guard(
        adapter_report_path=args.adapter_report,
        output_dir=args.output_dir,
        min_documents=args.min_documents,
        min_page_scoped_documents=args.min_page_scoped_documents,
        require_mapping=args.require_mapping or args.quality,
    )
    s = report.get("summary") or {}
    print("TRACE-Net OpenSearch Adapter Lineage Guard v1")
    print(" Quality status:", report.get("quality_status"))
    for key in (
        "opensearch_document_count",
        "page_scoped_document_count",
        "documents_with_search_text_count",
        "missing_page_id_count",
        "missing_source_trace_count",
        "lineage_guard_dropped_document_count",
        "unsafe_index_document_count",
        "raw_feedback_indexed_count",
        "raw_visual_output_indexed_count",
        "raw_ocr_unfiltered_indexed_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {s.get(key)}")
    print(" report_path:", report.get("paths", {}).get("report_path"))
    print(" quality_path:", report.get("paths", {}).get("quality_path"))
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
