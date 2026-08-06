"""TRACE-Net OpenSearch Missing Lineage Inspector v1.

This module inspects an already-built TRACE-Net OpenSearch Adapter v1 report
and emits a focused diagnostic artifact for documents that are missing page
lineage or source-trace lineage.

Safety contract:
- Reads local JSON artifacts only.
- Writes only local diagnostic JSON/Markdown files under the requested output dir.
- Does not write to Postgres, Qdrant, or OpenSearch.
- Does not mutate source truth.
- Does not grant answer permission and cannot prove claims.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_opensearch_missing_lineage_inspector_v1"
ALGORITHM = "trace_net_opensearch_missing_lineage_inspector_v1"
DEFAULT_ADAPTER_PATH = (
    "local_data/organization/trace_net/opensearch_adapter/"
    "trace_net_opensearch_adapter_v1.json"
)
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/opensearch_missing_lineage_inspector"
DOCUMENT_KEYS = (
    "documents",
    "opensearch_documents",
    "safe_documents",
    "records",
)
TEXT_KEYS = (
    "text",
    "content",
    "body",
    "search_text",
    "chunk_text",
    "clean_snippet",
    "summary",
    "title",
)
PAGE_FIELD_PATHS = (
    "page_id",
    "source_page_id",
    "source_page_ids",
    "parent_page_id",
    "canonical_page_id",
    "metadata.page_id",
    "metadata.source_page_id",
    "metadata.source_page_ids",
    "source.page_id",
    "source.source_page_id",
    "source.source_page_ids",
    "source_trace.page_id",
    "source_trace.source_page_id",
    "source_trace.page_ids",
    "source_trace.source_page_ids",
    "payload.page_id",
    "payload.source_page_id",
    "payload.source_page_ids",
    "properties.page_id",
    "properties.source_page_id",
    "properties.source_page_ids",
)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON artifact: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected top-level JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def clean_strings(values: Iterable[Any]) -> list[str]:
    out: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            out.add(text)
    return sorted(out)


def get_nested(record: dict[str, Any], path: str) -> Any:
    cur: Any = record
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def find_documents(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in DOCUMENT_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    raise KeyError(f"Could not find OpenSearch document list. Tried keys: {DOCUMENT_KEYS}")


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "present"}
    return bool(value)


def page_values_from_doc(doc: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for path in PAGE_FIELD_PATHS:
        value = get_nested(doc, path)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        else:
            values.append(value)
    return clean_strings(values)


def has_page_lineage(doc: dict[str, Any]) -> bool:
    return bool(page_values_from_doc(doc))


def has_source_trace_lineage(doc: dict[str, Any]) -> bool:
    if boolish(doc.get("source_trace_present")):
        return True

    trace = doc.get("source_trace")
    if isinstance(trace, dict):
        if page_values_from_doc({"source_trace": trace}):
            return True
        for key in ("source_package_entry", "source_uri", "source_url", "source_file_id"):
            if trace.get(key) not in (None, "", [], {}):
                return True
    elif isinstance(trace, str) and trace.strip():
        return True

    # Adapter v1 currently models source trace as page scope. A document with
    # page_id/source_page_ids is considered source-trace present for this exact
    # search handoff, because the graph/API resolves the page to the actual
    # source package later.
    return has_page_lineage(doc)


def possible_page_fields(doc: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for path in PAGE_FIELD_PATHS:
        value = get_nested(doc, path)
        if value not in (None, "", [], {}):
            found[path] = value
    return found


def text_preview(doc: dict[str, Any], limit: int = 500) -> str:
    for key in TEXT_KEYS:
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())[:limit]
    return ""


def document_id(doc: dict[str, Any]) -> str | None:
    for key in ("opensearch_document_id", "document_id", "doc_id", "id"):
        value = doc.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def document_type(doc: dict[str, Any]) -> str:
    for key in ("document_type", "record_type", "bucket", "type"):
        value = doc.get(key)
        if value not in (None, ""):
            return str(value)
    return "unknown"


def inspect_documents(docs: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    doc_type_counts: Counter[str] = Counter()
    missing_doc_type_counts: Counter[str] = Counter()
    rag_bucket_counts: Counter[str] = Counter()
    missing_rag_bucket_counts: Counter[str] = Counter()

    missing_page_id_count = 0
    missing_source_trace_count = 0

    for index, doc in enumerate(docs):
        dtype = document_type(doc)
        bucket = str(doc.get("rag_bucket") or "unknown")
        doc_type_counts[dtype] += 1
        rag_bucket_counts[bucket] += 1

        page_ok = has_page_lineage(doc)
        trace_ok = has_source_trace_lineage(doc)

        if not page_ok:
            missing_page_id_count += 1
        if not trace_ok:
            missing_source_trace_count += 1

        if page_ok and trace_ok:
            continue

        missing_doc_type_counts[dtype] += 1
        missing_rag_bucket_counts[bucket] += 1
        records.append(
            {
                "index": index,
                "opensearch_document_id": document_id(doc),
                "document_type": dtype,
                "rag_bucket": doc.get("rag_bucket"),
                "authority": doc.get("authority"),
                "retrieval_only": doc.get("retrieval_only"),
                "answer_support_candidate": doc.get("answer_support_candidate"),
                "page_id": doc.get("page_id"),
                "source_page_ids": doc.get("source_page_ids"),
                "source_trace_present": doc.get("source_trace_present"),
                "possible_page_fields": possible_page_fields(doc),
                "community_ids": doc.get("community_ids"),
                "part_numbers": doc.get("part_numbers"),
                "source_artifact": doc.get("source_artifact"),
                "safe_for_opensearch": doc.get("safe_for_opensearch"),
                "can_answer_directly": doc.get("can_answer_directly"),
                "can_prove_claims": doc.get("can_prove_claims"),
                "can_mutate_source_truth": doc.get("can_mutate_source_truth"),
                "text_preview": text_preview(doc),
                "top_level_keys": sorted(str(k) for k in doc.keys()),
            }
        )

    summary = {
        "opensearch_document_count": len(docs),
        "page_scoped_document_count": sum(1 for d in docs if has_page_lineage(d)),
        "missing_lineage_doc_count": len(records),
        "missing_page_id_count": missing_page_id_count,
        "missing_source_trace_count": missing_source_trace_count,
        "document_type_counts": dict(sorted(doc_type_counts.items())),
        "missing_lineage_document_type_counts": dict(sorted(missing_doc_type_counts.items())),
        "rag_bucket_counts": dict(sorted(rag_bucket_counts.items())),
        "missing_lineage_rag_bucket_counts": dict(sorted(missing_rag_bucket_counts.items())),
        "unsafe_index_document_count": sum(1 for d in docs if not d.get("safe_for_opensearch", True)),
        "raw_feedback_indexed_count": sum(1 for d in docs if d.get("raw_feedback_indexed")),
        "raw_visual_output_indexed_count": sum(1 for d in docs if d.get("raw_visual_output")),
        "raw_ocr_unfiltered_indexed_count": sum(1 for d in docs if d.get("raw_ocr_unfiltered")),
        "retrieval_only_answer_allowed_count": sum(
            1
            for d in docs
            if d.get("retrieval_only")
            and (d.get("can_answer_directly") or d.get("can_prove_claims"))
        ),
        "source_truth_mutation_allowed_count": sum(
            1 for d in docs if d.get("source_truth_mutation_allowed") or d.get("can_mutate_source_truth")
        ),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "can_answer_directly_count": sum(1 for d in docs if d.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for d in docs if d.get("can_prove_claims")),
        "can_mutate_source_truth_count": sum(1 for d in docs if d.get("can_mutate_source_truth")),
    }
    return summary, records


def adapter_quality_status(payload: dict[str, Any]) -> str | None:
    value = payload.get("quality_status") or payload.get("status")
    if isinstance(value, str):
        return value
    quality = payload.get("quality")
    if isinstance(quality, dict):
        qvalue = quality.get("quality_status") or quality.get("status")
        if isinstance(qvalue, str):
            return qvalue
    return None


def quality_report(
    report: dict[str, Any],
    *,
    min_documents: int = 1,
    max_missing_lineage_docs: int | None = None,
    require_adapter_quality_pass: bool = False,
) -> dict[str, Any]:
    summary = report.get("summary") or {}
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, value: Any, expected: str, severity: str = "critical") -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "value": value,
                "expected": expected,
                "severity": severity,
            }
        )

    add(
        "document_count_min",
        int(summary.get("opensearch_document_count", 0)) >= min_documents,
        summary.get("opensearch_document_count", 0),
        f">= {min_documents}",
    )
    if max_missing_lineage_docs is not None:
        add(
            "missing_lineage_doc_count_max",
            int(summary.get("missing_lineage_doc_count", 0)) <= max_missing_lineage_docs,
            summary.get("missing_lineage_doc_count", 0),
            f"<= {max_missing_lineage_docs}",
        )
    if require_adapter_quality_pass:
        add(
            "adapter_quality_pass",
            str(summary.get("adapter_quality_status") or "").upper() == "PASS",
            summary.get("adapter_quality_status"),
            "PASS",
        )

    add("postgres_write_attempt_count_zero", summary.get("postgres_write_attempt_count") == 0, summary.get("postgres_write_attempt_count"), "0")
    add("qdrant_write_attempt_count_zero", summary.get("qdrant_write_attempt_count") == 0, summary.get("qdrant_write_attempt_count"), "0")
    add("opensearch_write_attempt_count_zero", summary.get("opensearch_write_attempt_count") == 0, summary.get("opensearch_write_attempt_count"), "0")
    add("source_truth_mutation_allowed_count_zero", summary.get("source_truth_mutation_allowed_count") == 0, summary.get("source_truth_mutation_allowed_count"), "0")
    add("can_answer_directly_count_zero", summary.get("can_answer_directly_count") == 0, summary.get("can_answer_directly_count"), "0")
    add("can_prove_claims_count_zero", summary.get("can_prove_claims_count") == 0, summary.get("can_prove_claims_count"), "0")
    add("can_mutate_source_truth_count_zero", summary.get("can_mutate_source_truth_count") == 0, summary.get("can_mutate_source_truth_count"), "0")

    failed = [c for c in checks if not c["passed"] and c.get("severity") == "critical"]
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": "PASS" if not failed else "FAIL",
        "quality_status": "PASS" if not failed else "FAIL",
        "generated_at": now_iso(),
        "checks": checks,
        "summary": {**summary, "failed_check_count": len(failed)},
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# TRACE-Net OpenSearch Missing Lineage Inspector v1",
        "",
        f"**Status:** {report.get('status')}",
        f"**Quality:** {report.get('quality_status')}",
        f"**Adapter quality:** {summary.get('adapter_quality_status')}",
        "",
        "## Summary",
        "",
    ]
    for key in (
        "opensearch_document_count",
        "page_scoped_document_count",
        "missing_lineage_doc_count",
        "missing_page_id_count",
        "missing_source_trace_count",
        "unsafe_index_document_count",
        "raw_feedback_indexed_count",
        "raw_visual_output_indexed_count",
        "raw_ocr_unfiltered_indexed_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Missing lineage by document type", ""])
    missing_type_counts = summary.get("missing_lineage_document_type_counts") or {}
    if missing_type_counts:
        for key, value in sorted(missing_type_counts.items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Safety Contract",
            "",
            "- Diagnostic artifact only; no Postgres writes.",
            "- Diagnostic artifact only; no Qdrant writes.",
            "- Diagnostic artifact only; no OpenSearch writes.",
            "- Does not mutate source truth.",
            "- Does not grant answer permission or proof authority.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_missing_lineage_inspection(
    *,
    adapter_path: str | Path = DEFAULT_ADAPTER_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    min_documents: int = 1,
    max_missing_lineage_docs: int | None = None,
    require_adapter_quality_pass: bool = False,
    write_quality: bool = False,
) -> dict[str, Any]:
    adapter_payload = read_json(adapter_path)
    docs = find_documents(adapter_payload)
    summary, records = inspect_documents(docs)
    summary["schema_version"] = SCHEMA_VERSION
    summary["algorithm"] = ALGORITHM
    summary["adapter_path"] = str(adapter_path)
    summary["adapter_quality_status"] = adapter_quality_status(adapter_payload)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_opensearch_missing_lineage_inspector_v1.json"
    quality_path = out / "trace_net_opensearch_missing_lineage_inspector_v1_quality.json"
    markdown_path = out / "trace_net_opensearch_missing_lineage_inspector_v1.md"

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "NO_MISSING_LINEAGE" if not records else "MISSING_LINEAGE_FOUND",
        "quality_status": "UNKNOWN",
        "generated_at": now_iso(),
        "summary": summary,
        "records": records,
        "paths": {
            "report_path": str(report_path),
            "quality_path": str(quality_path),
            "markdown_path": str(markdown_path),
        },
    }
    quality = quality_report(
        report,
        min_documents=min_documents,
        max_missing_lineage_docs=max_missing_lineage_docs,
        require_adapter_quality_pass=require_adapter_quality_pass,
    )
    report["quality"] = quality
    report["quality_status"] = quality["quality_status"]
    report["summary"]["quality_status"] = quality["quality_status"]

    write_json(report_path, report)
    write_json(quality_path, quality)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    if write_quality:
        write_json(quality_path, quality)
    return report


def check_existing_report(
    *,
    report_path: str | Path,
    min_documents: int = 1,
    max_missing_lineage_docs: int | None = None,
    require_adapter_quality_pass: bool = False,
    write_json_flag: bool = False,
) -> dict[str, Any]:
    report = read_json(report_path)
    quality = quality_report(
        report,
        min_documents=min_documents,
        max_missing_lineage_docs=max_missing_lineage_docs,
        require_adapter_quality_pass=require_adapter_quality_pass,
    )
    report["quality"] = quality
    report["quality_status"] = quality["quality_status"]
    report.setdefault("summary", {})["quality_status"] = quality["quality_status"]
    if write_json_flag:
        write_json(report_path, report)
        paths = report.get("paths") if isinstance(report.get("paths"), dict) else {}
        quality_path = paths.get("quality_path") or str(Path(report_path).with_name("trace_net_opensearch_missing_lineage_inspector_v1_quality.json"))
        write_json(quality_path, quality)
    return report


def add_common_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-documents", type=int, default=1)
    parser.add_argument("--max-missing-lineage-docs", type=int, default=None)
    parser.add_argument("--require-adapter-quality-pass", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net OpenSearch missing-lineage inspection artifact.")
    parser.add_argument("--opensearch-adapter", "--adapter", default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--quality", action="store_true")
    add_common_quality_args(parser)
    args = parser.parse_args(argv)

    report = build_missing_lineage_inspection(
        adapter_path=args.opensearch_adapter,
        output_dir=args.output_dir,
        min_documents=args.min_documents,
        max_missing_lineage_docs=args.max_missing_lineage_docs,
        require_adapter_quality_pass=args.require_adapter_quality_pass,
        write_quality=args.quality,
    )
    summary = report["summary"]
    print("TRACE-Net OpenSearch Missing Lineage Inspector v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in (
        "opensearch_document_count",
        "page_scoped_document_count",
        "missing_lineage_doc_count",
        "missing_page_id_count",
        "missing_source_trace_count",
        "unsafe_index_document_count",
        "raw_feedback_indexed_count",
        "raw_visual_output_indexed_count",
        "raw_ocr_unfiltered_indexed_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report['paths']['report_path']}")
    print(f" quality_path: {report['paths']['quality_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
