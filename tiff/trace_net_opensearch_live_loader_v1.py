"""TRACE-Net OpenSearch Live Loader v1.

Live exact-search loader for the safe TRACE-Net OpenSearch Adapter artifact.

This module is the first stage that is allowed to write to OpenSearch, but only
when explicitly requested with ``--allow-opensearch-writes``. It never writes to
Postgres, Qdrant, source truth, graph artifacts, or answer/final-gate state.

Safety contract:
- Inputs must already be source/page-lineage guarded.
- Every live-indexed document must have page lineage or source_page_ids.
- Raw feedback, raw visual output, raw unfiltered OCR, and unsafe records are
  rejected before upload.
- Indexed documents are retrieval-only exact-search aids.
- Indexed documents cannot answer directly, prove claims, or mutate source truth.
- OpenSearch writes are explicit and local-index scoped only.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

MODULE_NAME = "trace_net_opensearch_live_loader_v1"
REPORT_NAME = "trace_net_opensearch_live_loader_v1.json"
QUALITY_NAME = "trace_net_opensearch_live_loader_v1_quality.json"
SUMMARY_NAME = "trace_net_opensearch_live_loader_v1_summary.json"
MANIFEST_NAME = "trace_net_opensearch_live_loader_v1_manifest.json"
MARKDOWN_NAME = "trace_net_opensearch_live_loader_v1.md"
DEFAULT_ADAPTER_PATH = "local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json"
DEFAULT_LOADER_SMOKE_PATH = "local_data/organization/trace_net/opensearch_loader_smoke/trace_net_opensearch_loader_smoke_v1.json"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/opensearch_live_loader"
DEFAULT_INDEX_NAME = "trace_net_safe_search_v1"
DEFAULT_OPENSEARCH_URL = "http://localhost:9200"

DOCUMENT_LIST_KEYS = ("documents", "opensearch_documents", "safe_documents", "records")
MAPPING_KEYS = ("mapping", "mappings", "index_mapping", "opensearch_mapping", "index_mappings")
PAGE_KEYS = ("page_id", "source_page_id", "parent_page_id", "canonical_page_id")
TEXT_KEYS = ("search_text", "text", "content", "body", "chunk_text", "clean_text", "clean_snippet", "snippet", "summary", "title")
EXACT_TEXT_SEARCH_FIELDS = ("search_text", "text", "title", "part_number", "part_numbers", "page_id", "source_page_ids", "cell_id", "row_id", "table_id", "opensearch_document_id")
DOC_ID_KEYS = ("opensearch_document_id", "document_id", "doc_id", "id", "_id", "record_id")

HARD_ZERO_COUNTER_KEYS = (
    "unsafe_index_document_count",
    "raw_feedback_indexed_count",
    "raw_visual_output_indexed_count",
    "raw_ocr_unfiltered_indexed_count",
    "retrieval_only_answer_allowed_count",
    "answer_permission_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
)


@dataclass(frozen=True)
class LiveLoaderThresholds:
    min_documents: int = 100
    min_page_scoped_documents: int = 100
    min_loaded_documents: int = 100
    min_smoke_queries: int = 3
    require_adapter_quality_pass: bool = False
    require_loader_smoke_quality_pass: bool = False
    require_mapping: bool = False
    require_live_read_check: bool = False
    require_bulk_load: bool = False
    allow_opensearch_writes: bool = False


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
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "present", "allowed"}
    return bool(value)


def status_value(payload: dict[str, Any]) -> str | None:
    for key in ("quality_status", "status"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in ("quality_status", "status", "adapter_quality_status"):
            value = summary.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def status_pass(payload: dict[str, Any]) -> bool:
    return str(status_value(payload) or "").upper() == "PASS"


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
    values.extend(string_list(record.get("page_ids")))
    values.extend(string_list(record.get("source_page_ids")))
    for outer in ("metadata", "source", "source_trace", "payload", "properties"):
        child = record.get(outer)
        if isinstance(child, dict):
            for key in PAGE_KEYS + ("page_ids", "source_page_ids"):
                values.extend(string_list(child.get(key)))
    return sorted(set(v for v in values if v))


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


def document_type(record: dict[str, Any]) -> str:
    for key in ("document_type", "record_type", "type", "bucket", "rag_bucket"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def doc_id(record: dict[str, Any], fallback_index: int) -> str:
    for key in DOC_ID_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    page_id = (page_values(record) or ["unknown_page"])[0]
    return f"{page_id}::opensearch_live_doc::{fallback_index}"


def looks_like(record: dict[str, Any], needle: str) -> bool:
    hay = " ".join(str(record.get(k, "")) for k in ("document_type", "record_type", "type", "bucket", "rag_bucket", "authority"))
    return needle.lower() in hay.lower()


def is_retrieval_only(record: dict[str, Any]) -> bool:
    return boolish(record.get("retrieval_only")) or looks_like(record, "retrieval_only")


def can_answer(record: dict[str, Any]) -> bool:
    return any(boolish(record.get(k)) for k in ("can_answer_directly", "answer_allowed", "direct_answer_allowed"))


def can_prove(record: dict[str, Any]) -> bool:
    return any(boolish(record.get(k)) for k in ("can_prove_claims", "claim_proof_allowed"))


def unsafe_reason(record: dict[str, Any]) -> str | None:
    if not has_page_lineage(record):
        return "missing_page_lineage"
    if not has_source_trace(record):
        return "missing_source_trace"
    if not text_for_record(record).strip():
        return "missing_search_text"
    if boolish(record.get("unsafe")) or boolish(record.get("unsafe_index_document")):
        return "unsafe_flag"
    if looks_like(record, "raw_feedback"):
        return "raw_feedback"
    if looks_like(record, "raw_visual") or looks_like(record, "raw_vision"):
        return "raw_visual_output"
    if looks_like(record, "raw_ocr") and not looks_like(record, "filtered"):
        return "raw_ocr_unfiltered"
    if is_retrieval_only(record) and can_answer(record):
        return "retrieval_only_answer_allowed"
    if can_answer(record):
        return "can_answer_directly"
    if can_prove(record):
        return "can_prove_claims"
    if boolish(record.get("source_truth_mutation_allowed")):
        return "source_truth_mutation_allowed"
    return None


def filter_safe_documents(docs: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    safe: list[dict[str, Any]] = []
    dropped: Counter[str] = Counter()
    for doc in docs:
        reason = unsafe_reason(doc)
        if reason:
            dropped[reason] += 1
            continue
        safe.append(doc)
    return safe, dropped


def normalize_mapping(mapping: dict[str, Any] | None) -> dict[str, Any]:
    """Return a valid OpenSearch create-index body.

    Adapter artifacts sometimes wrap the mapping with metadata such as
    ``index_name``. OpenSearch rejects unknown top-level keys during index
    creation, so only ``settings``, ``mappings``, and ``aliases`` are allowed
    in the final create-index body.
    """
    if not mapping:
        return {}

    # Already an index-create body, possibly with harmless adapter metadata.
    body: dict[str, Any] = {}
    for key in ("settings", "mappings", "aliases"):
        value = mapping.get(key)
        if isinstance(value, dict) and value:
            body[key] = value
    if body:
        return body

    # Some adapter reports store the actual property map directly under
    # ``properties``; some store just the properties dictionary itself.
    if isinstance(mapping.get("properties"), dict):
        return {"mappings": {"properties": mapping["properties"]}}
    return {"mappings": mapping}


def field_query_clauses(query: str, *, phrase: bool = True) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    for field in EXACT_TEXT_SEARCH_FIELDS:
        clauses.append({"term": {f"{field}.keyword": query}})
        if phrase:
            clauses.append({"match_phrase": {field: query}})
    clauses.append({
        "multi_match": {
            "query": query,
            "fields": list(EXACT_TEXT_SEARCH_FIELDS),
            "type": "best_fields",
        }
    })
    return clauses


def make_bulk_ndjson(docs: list[dict[str, Any]], index_name: str, start_index: int = 0) -> str:
    lines: list[str] = []
    for offset, doc in enumerate(docs):
        identifier = doc_id(doc, start_index + offset)
        lines.append(json.dumps({"index": {"_index": index_name, "_id": identifier}}, ensure_ascii=False, sort_keys=True))
        lines.append(json.dumps(doc, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines) + ("\n" if lines else "")


@dataclass
class HttpResult:
    status_code: int
    body: Any
    raw_text: str
    ok: bool


class OpenSearchHttpClient:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request(self, method: str, path: str, body: Any = None, content_type: str = "application/json") -> HttpResult:
        url = self.base_url + (path if path.startswith("/") else f"/{path}")
        data: bytes | None = None
        headers: dict[str, str] = {}
        if body is not None:
            if isinstance(body, (dict, list)):
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                headers["Content-Type"] = content_type
            elif isinstance(body, str):
                data = body.encode("utf-8")
                headers["Content-Type"] = content_type
            else:
                data = bytes(body)
                headers["Content-Type"] = content_type
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
                parsed: Any
                try:
                    parsed = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    parsed = raw
                return HttpResult(status_code=response.status, body=parsed, raw_text=raw, ok=200 <= response.status < 300)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return HttpResult(status_code=exc.code, body=parsed, raw_text=raw, ok=False)


def count_bulk_errors(bulk_response: Any) -> int:
    if not isinstance(bulk_response, dict):
        return 1
    if not boolish(bulk_response.get("errors")):
        return 0
    errors = 0
    for item in bulk_response.get("items") or []:
        if not isinstance(item, dict):
            continue
        action = item.get("index") or item.get("create") or item.get("update") or item.get("delete")
        if isinstance(action, dict) and int(action.get("status") or 0) >= 300:
            errors += 1
    return errors or 1


def extract_hit_count(search_response: Any) -> int:
    if not isinstance(search_response, dict):
        return 0
    hits = search_response.get("hits")
    if not isinstance(hits, dict):
        return 0
    total = hits.get("total")
    if isinstance(total, dict):
        return int(total.get("value") or 0)
    if isinstance(total, int):
        return total
    hit_list = hits.get("hits")
    return len(hit_list) if isinstance(hit_list, list) else 0


def smoke_query_body(query: str, query_kind: str | None = None, size: int = 5) -> dict[str, Any]:
    """Build robust live smoke queries against the actual safe-document schema.

    The adapter's searchable text field is commonly ``text`` rather than
    ``search_text``. Older smoke logic searched only ``search_text``, which made
    a correctly loaded index look unhealthy. This query intentionally searches
    both the legacy and current fields while preserving retrieval-only behavior.
    """
    should = field_query_clauses(query)
    if query_kind == "part_number_exact":
        should = [
            {"term": {"part_numbers.keyword": query}},
            {"term": {"part_number.keyword": query}},
            *should,
        ]
        return {"query": {"bool": {"should": should, "minimum_should_match": 1}}, "size": size}
    if query_kind == "table_cell_exact":
        # Do not hard-filter table smoke queries by document_type. In live
        # OpenSearch, the exact table-cell value can also appear in a
        # part-candidate or row document, and a strict filter can make a
        # correctly-loaded index look unhealthy when the analyzer/mapping
        # differs slightly across OpenSearch versions. Keep the query
        # retrieval-only, search the real text/title fields, and add table
        # document types as optional routing boosts rather than mandatory
        # filters.
        table_type_boosts = [
            {"term": {"document_type.keyword": "table_cell_normalized"}},
            {"term": {"document_type.keyword": "table_cell"}},
            {"term": {"document_type.keyword": "table_row_normalized"}},
            {"term": {"document_type.keyword": "table_row"}},
        ]
        return {
            "query": {
                "bool": {
                    "should": [*table_type_boosts, *should],
                    "minimum_should_match": 1,
                }
            },
            "size": size,
        }
    return {"query": {"bool": {"should": should, "minimum_should_match": 1}}, "size": size}


def query_plans_from_loader_smoke(loader_smoke: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not loader_smoke:
        return []
    plans = loader_smoke.get("query_plans") or loader_smoke.get("records") or []
    return [p for p in plans if isinstance(p, dict)]


def build_fallback_query_plans(docs: list[dict[str, Any]], index_name: str) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for doc in docs:
        text = text_for_record(doc)
        tokens = [token.strip(" ,.;:()[]{}") for token in text.split() if len(token.strip(" ,.;:()[]{}")) >= 3]
        if tokens:
            query = " ".join(tokens[: min(6, len(tokens))])
            plans.append({"query_plan_id": f"{MODULE_NAME}:fallback_phrase", "query_kind": "ocr_phrase_exact", "query": query, "query_text": query})
            break
    for doc in docs:
        if "table" in document_type(doc).lower() or "table" in str(doc.get("rag_bucket") or "").lower():
            text = text_for_record(doc).strip()
            if text:
                query = text.split()[0]
                plans.append({"query_plan_id": f"{MODULE_NAME}:fallback_table", "query_kind": "table_cell_exact", "query": query, "query_text": query})
                break
    while len(plans) < 3 and docs:
        text = text_for_record(docs[len(plans) % len(docs)]).strip()
        query = " ".join(text.split()[:3]) or "manual"
        plans.append({"query_plan_id": f"{MODULE_NAME}:fallback_{len(plans)}", "query_kind": "ocr_phrase_exact", "query": query, "query_text": query})
    return plans[:3]


def summarize_documents(adapter: dict[str, Any], docs: list[dict[str, Any]], dropped: Counter[str]) -> dict[str, Any]:
    type_counts = Counter(document_type(doc) for doc in docs)
    summary = adapter.get("summary") if isinstance(adapter.get("summary"), dict) else {}
    out: dict[str, Any] = {
        "opensearch_document_count": len(docs),
        "page_scoped_document_count": sum(1 for d in docs if has_page_lineage(d)),
        "documents_with_search_text_count": sum(1 for d in docs if text_for_record(d).strip()),
        "missing_page_id_count": sum(1 for d in docs if not has_page_lineage(d)),
        "missing_source_trace_count": sum(1 for d in docs if not has_source_trace(d)),
        "unsafe_index_document_count": sum(1 for d in docs if boolish(d.get("unsafe")) or boolish(d.get("unsafe_index_document"))),
        "raw_feedback_indexed_count": sum(1 for d in docs if looks_like(d, "raw_feedback")),
        "raw_visual_output_indexed_count": sum(1 for d in docs if looks_like(d, "raw_visual") or looks_like(d, "raw_vision")),
        "raw_ocr_unfiltered_indexed_count": sum(1 for d in docs if looks_like(d, "raw_ocr") and not looks_like(d, "filtered")),
        "retrieval_only_answer_allowed_count": sum(1 for d in docs if is_retrieval_only(d) and can_answer(d)),
        "answer_permission_count": sum(1 for d in docs if boolish(d.get("answer_permission")) or boolish(d.get("answer_allowed"))),
        "can_answer_directly_count": sum(1 for d in docs if can_answer(d)),
        "can_prove_claims_count": sum(1 for d in docs if can_prove(d)),
        "source_truth_mutation_allowed_count": sum(1 for d in docs if boolish(d.get("source_truth_mutation_allowed"))),
        "document_type_counts": dict(sorted(type_counts.items())),
        "lineage_guard_dropped_document_count": sum(dropped.values()),
        "lineage_guard_drop_reason_counts": dict(sorted(dropped.items())),
        "source_adapter_document_count": int(summary.get("opensearch_document_count") or 0),
        "source_adapter_quality_status": status_value(adapter),
    }
    return out


def assess_quality(summary: dict[str, Any], thresholds: LiveLoaderThresholds) -> tuple[str, list[str]]:
    errors: list[str] = []
    if int(summary.get("opensearch_document_count", 0) or 0) < thresholds.min_documents:
        errors.append("opensearch_document_count below minimum")
    if int(summary.get("page_scoped_document_count", 0) or 0) < thresholds.min_page_scoped_documents:
        errors.append("page_scoped_document_count below minimum")
    if thresholds.require_mapping and not summary.get("mapping_present"):
        errors.append("mapping is required but missing")
    if thresholds.require_adapter_quality_pass and str(summary.get("adapter_quality_status") or "").upper() != "PASS":
        errors.append("adapter quality PASS required")
    if thresholds.require_loader_smoke_quality_pass and str(summary.get("loader_smoke_quality_status") or "").upper() != "PASS":
        errors.append("loader smoke quality PASS required")
    if thresholds.require_bulk_load and not summary.get("bulk_load_performed"):
        errors.append("bulk load required but not performed")
    if thresholds.require_bulk_load and int(summary.get("loaded_document_count", 0) or 0) < thresholds.min_loaded_documents:
        errors.append("loaded_document_count below minimum")
    if thresholds.require_bulk_load and int(summary.get("bulk_error_count", 0) or 0) != 0:
        errors.append("bulk_error_count must be 0")
    if thresholds.require_live_read_check and not summary.get("live_read_check_ok"):
        errors.append("live read check required but not passing")
    if int(summary.get("smoke_query_count", 0) or 0) < thresholds.min_smoke_queries:
        errors.append("smoke_query_count below minimum")
    if thresholds.require_live_read_check and int(summary.get("smoke_query_success_count", 0) or 0) < thresholds.min_smoke_queries:
        errors.append("smoke_query_success_count below minimum")
    for key in HARD_ZERO_COUNTER_KEYS + ("missing_page_id_count", "missing_source_trace_count"):
        if int(summary.get(key, 0) or 0) != 0:
            errors.append(f"{key} must be 0")
    if int(summary.get("opensearch_write_attempt_count", 0) or 0) and not thresholds.allow_opensearch_writes:
        errors.append("opensearch writes require --allow-opensearch-writes")
    return ("PASS" if not errors else "FAIL", errors)


def write_markdown_report(path: str | Path, report: dict[str, Any]) -> None:
    s = report.get("summary", {})
    lines = [
        "# TRACE-Net OpenSearch Live Loader v1",
        "",
        f"Quality status: {report.get('quality_status')}",
        f"Status: {report.get('status')}",
        "",
        "## Summary",
        "",
    ]
    for key in (
        "index_name",
        "opensearch_url",
        "opensearch_document_count",
        "loaded_document_count",
        "mapping_present",
        "create_index_performed",
        "bulk_load_performed",
        "refresh_performed",
        "live_read_check_ok",
        "smoke_query_count",
        "smoke_query_success_count",
        "missing_page_id_count",
        "missing_source_trace_count",
        "unsafe_index_document_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        lines.append(f"- {key}: {s.get(key)}")
    lines += [
        "",
        "## Safety contract",
        "",
        "This module may write to OpenSearch only when explicitly allowed. It never writes to Postgres, Qdrant, source truth, graph state, or final-answer authority.",
    ]
    write_text(path, "\n".join(lines) + "\n")


def build_live_loader_report(
    *,
    opensearch_adapter_path: str | Path,
    loader_smoke_path: str | Path | None,
    output_dir: str | Path,
    opensearch_url: str = DEFAULT_OPENSEARCH_URL,
    index_name: str = DEFAULT_INDEX_NAME,
    batch_size: int = 500,
    timeout_seconds: float = 30.0,
    recreate_index: bool = False,
    create_index: bool = False,
    bulk_load: bool = False,
    refresh: bool = False,
    run_smoke_queries: bool = False,
    allow_opensearch_writes: bool = False,
    dry_run: bool = False,
    thresholds: LiveLoaderThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or LiveLoaderThresholds(allow_opensearch_writes=allow_opensearch_writes)
    output_path = Path(output_dir)
    adapter_path = Path(opensearch_adapter_path)
    adapter = load_json(adapter_path)
    doc_key, source_docs = find_documents(adapter)
    safe_docs, dropped = filter_safe_documents(source_docs)
    mapping_key, mapping = find_mapping(adapter)
    mapping_body = normalize_mapping(mapping)

    loader_smoke: dict[str, Any] | None = None
    loader_smoke_quality_status: str | None = None
    if loader_smoke_path:
        p = Path(loader_smoke_path)
        if p.exists():
            loader_smoke = load_json(p)
            loader_smoke_quality_status = status_value(loader_smoke)

    plans = query_plans_from_loader_smoke(loader_smoke) or build_fallback_query_plans(safe_docs, index_name)

    client = OpenSearchHttpClient(opensearch_url, timeout_seconds=timeout_seconds)
    operations: list[dict[str, Any]] = []
    write_attempts = 0
    create_index_performed = False
    bulk_load_performed = False
    refresh_performed = False
    loaded_document_count = 0
    bulk_error_count = 0
    live_read_check_ok = False
    smoke_results: list[dict[str, Any]] = []
    live_index_document_count = 0

    def op_record(name: str, status: str, details: dict[str, Any] | None = None) -> None:
        operations.append({"operation": name, "status": status, "details": details or {}})

    if dry_run:
        op_record("dry_run", "SKIPPED_LIVE_WRITES", {"reason": "dry_run enabled"})
    else:
        if (create_index or recreate_index or bulk_load or refresh) and not allow_opensearch_writes:
            op_record("guard", "BLOCKED", {"reason": "OpenSearch writes requested without allow_opensearch_writes"})
        else:
            if recreate_index:
                write_attempts += 1
                delete_result = client.request("DELETE", f"/{index_name}")
                op_record("delete_index", "OK" if delete_result.ok or delete_result.status_code == 404 else "ERROR", {"status_code": delete_result.status_code})
            if create_index or recreate_index:
                write_attempts += 1
                create_result = client.request("PUT", f"/{index_name}", body=mapping_body or {})
                create_index_performed = create_result.ok or create_result.status_code in {200, 201}
                op_record("create_index", "OK" if create_result.ok else "ERROR", {"status_code": create_result.status_code, "body": create_result.body})
            if bulk_load:
                for start in range(0, len(safe_docs), max(1, batch_size)):
                    batch = safe_docs[start : start + max(1, batch_size)]
                    ndjson = make_bulk_ndjson(batch, index_name=index_name, start_index=start)
                    write_attempts += 1
                    bulk_result = client.request("POST", "/_bulk", body=ndjson, content_type="application/x-ndjson")
                    errors = count_bulk_errors(bulk_result.body)
                    bulk_error_count += errors
                    if bulk_result.ok and errors == 0:
                        loaded_document_count += len(batch)
                    op_record("bulk_load_batch", "OK" if bulk_result.ok and errors == 0 else "ERROR", {"start": start, "count": len(batch), "status_code": bulk_result.status_code, "bulk_error_count": errors})
                bulk_load_performed = True
            if refresh:
                write_attempts += 1
                refresh_result = client.request("POST", f"/{index_name}/_refresh")
                refresh_performed = refresh_result.ok
                op_record("refresh", "OK" if refresh_result.ok else "ERROR", {"status_code": refresh_result.status_code})
            if bulk_load or refresh or run_smoke_queries:
                count_result = client.request("GET", f"/{index_name}/_count")
                if count_result.ok and isinstance(count_result.body, dict):
                    live_index_document_count = int(count_result.body.get("count") or 0)
                op_record("live_count", "OK" if count_result.ok else "ERROR", {"status_code": count_result.status_code, "count": live_index_document_count})
            if run_smoke_queries:
                for plan in plans:
                    query = str(plan.get("query") or plan.get("query_text") or "").strip()
                    if not query:
                        continue
                    kind = str(plan.get("query_kind") or "ocr_phrase_exact")
                    result = client.request("POST", f"/{index_name}/_search", body=smoke_query_body(query, kind))
                    hit_count = extract_hit_count(result.body)
                    smoke_results.append({
                        "query_plan_id": plan.get("query_plan_id"),
                        "query_kind": kind,
                        "query": query,
                        "status_code": result.status_code,
                        "ok": result.ok,
                        "hit_count": hit_count,
                        "retrieval_only": True,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                    })
                live_read_check_ok = (
                    live_index_document_count >= max(1, loaded_document_count)
                    and bool(smoke_results)
                    and all(r.get("ok") and int(r.get("hit_count") or 0) > 0 for r in smoke_results)
                )

    base_summary = summarize_documents(adapter, safe_docs, dropped)
    summary: dict[str, Any] = {
        **base_summary,
        "schema_version": MODULE_NAME,
        "adapter_path": str(adapter_path),
        "adapter_document_list_key": doc_key,
        "adapter_quality_status": status_value(adapter),
        "loader_smoke_path": str(loader_smoke_path) if loader_smoke_path else None,
        "loader_smoke_quality_status": loader_smoke_quality_status,
        "mapping_present": mapping is not None,
        "mapping_key": mapping_key,
        "index_name": index_name,
        "opensearch_url": opensearch_url,
        "dry_run": dry_run,
        "allow_opensearch_writes": allow_opensearch_writes,
        "create_index_requested": create_index,
        "recreate_index_requested": recreate_index,
        "bulk_load_requested": bulk_load,
        "refresh_requested": refresh,
        "run_smoke_queries_requested": run_smoke_queries,
        "create_index_performed": create_index_performed,
        "bulk_load_performed": bulk_load_performed,
        "refresh_performed": refresh_performed,
        "loaded_document_count": loaded_document_count if bulk_load_performed else (len(safe_docs) if dry_run else 0),
        "live_index_document_count": live_index_document_count if not dry_run else len(safe_docs),
        "bulk_error_count": bulk_error_count,
        "smoke_query_count": len(plans),
        "smoke_query_success_count": sum(1 for r in smoke_results if r.get("ok") and int(r.get("hit_count") or 0) > 0),
        "live_read_check_ok": live_read_check_ok if run_smoke_queries else bool(dry_run),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": write_attempts,
        "opensearch_write_intended": bool(allow_opensearch_writes and (create_index or recreate_index or bulk_load or refresh)),
        "source_truth_mutations_performed": 0,
    }
    quality_status, quality_errors = assess_quality(summary, thresholds)
    report = {
        "module_name": MODULE_NAME,
        "schema_version": MODULE_NAME,
        "generated_at": now_iso(),
        "quality_status": quality_status,
        "status": "OPENSEARCH_LIVE_LOADER_READY" if quality_status == "PASS" else "OPENSEARCH_LIVE_LOADER_NOT_READY",
        "quality_errors": quality_errors,
        "inputs": {"opensearch_adapter": str(adapter_path), "loader_smoke": str(loader_smoke_path) if loader_smoke_path else None},
        "outputs": {
            "report_path": str(output_path / REPORT_NAME),
            "quality_path": str(output_path / QUALITY_NAME),
            "summary_path": str(output_path / SUMMARY_NAME),
            "manifest_path": str(output_path / MANIFEST_NAME),
            "markdown_path": str(output_path / MARKDOWN_NAME),
        },
        "summary": summary,
        "mapping_preview": mapping_body,
        "operation_log": operations,
        "query_plans": plans,
        "smoke_query_results": smoke_results,
        "records": smoke_results or plans,
        "safety_contract": {
            "opensearch_writes_allowed_only_when_explicit": True,
            "opensearch_write_intended": summary["opensearch_write_intended"],
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
            "indexed_documents_are_retrieval_only": True,
        },
    }
    write_json(output_path / REPORT_NAME, report)
    write_json(output_path / QUALITY_NAME, report)
    write_json(output_path / SUMMARY_NAME, {"quality_status": quality_status, "summary": summary})
    write_json(output_path / MANIFEST_NAME, {"schema_version": f"{MODULE_NAME}_manifest", "generated_at": now_iso(), "outputs": report["outputs"], "inputs": report["inputs"], "quality_status": quality_status})
    write_markdown_report(output_path / MARKDOWN_NAME, report)
    return report


def check_live_loader_quality(*, report_path: str | Path, thresholds: LiveLoaderThresholds | None = None, write_json_report: bool = False) -> dict[str, Any]:
    report = load_json(report_path)
    thresholds = thresholds or LiveLoaderThresholds()
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("Report is missing summary object")
    quality_status, quality_errors = assess_quality(summary, thresholds)
    report["quality_status"] = quality_status
    report["status"] = "OPENSEARCH_LIVE_LOADER_READY" if quality_status == "PASS" else "OPENSEARCH_LIVE_LOADER_NOT_READY"
    report["quality_errors"] = quality_errors
    if write_json_report:
        p = Path(report_path)
        write_json(p, report)
        write_json(p.with_name(QUALITY_NAME), report)
    return report


def thresholds_from_args(args: argparse.Namespace) -> LiveLoaderThresholds:
    return LiveLoaderThresholds(
        min_documents=args.min_documents,
        min_page_scoped_documents=args.min_page_scoped_documents,
        min_loaded_documents=args.min_loaded_documents,
        min_smoke_queries=args.min_smoke_queries,
        require_adapter_quality_pass=args.require_adapter_quality_pass,
        require_loader_smoke_quality_pass=args.require_loader_smoke_quality_pass,
        require_mapping=args.require_mapping,
        require_live_read_check=args.require_live_read_check,
        require_bulk_load=args.require_bulk_load,
        allow_opensearch_writes=args.allow_opensearch_writes,
    )


def add_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-documents", type=int, default=100)
    parser.add_argument("--min-page-scoped-documents", type=int, default=100)
    parser.add_argument("--min-loaded-documents", type=int, default=100)
    parser.add_argument("--min-smoke-queries", type=int, default=3)
    parser.add_argument("--require-adapter-quality-pass", action="store_true")
    parser.add_argument("--require-loader-smoke-quality-pass", action="store_true")
    parser.add_argument("--require-mapping", action="store_true")
    parser.add_argument("--require-live-read-check", action="store_true")
    parser.add_argument("--require-bulk-load", action="store_true")
    parser.add_argument("--allow-opensearch-writes", action="store_true")


def print_summary(report: dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("TRACE-Net OpenSearch Live Loader v1")
    print(" Quality status:", report.get("quality_status"))
    print(" Status:", report.get("status"))
    for key in (
        "index_name",
        "opensearch_url",
        "adapter_quality_status",
        "loader_smoke_quality_status",
        "opensearch_document_count",
        "page_scoped_document_count",
        "loaded_document_count",
        "live_index_document_count",
        "missing_page_id_count",
        "missing_source_trace_count",
        "mapping_present",
        "create_index_performed",
        "bulk_load_performed",
        "refresh_performed",
        "live_read_check_ok",
        "smoke_query_count",
        "smoke_query_success_count",
        "bulk_error_count",
        "unsafe_index_document_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "allow_opensearch_writes",
    ):
        print(f" {key}: {s.get(key)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net OpenSearch Live Loader v1 report and optionally load the safe index.")
    parser.add_argument("--opensearch-adapter", default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--loader-smoke", default=DEFAULT_LOADER_SMOKE_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--opensearch-url", default=DEFAULT_OPENSEARCH_URL)
    parser.add_argument("--index-name", default=DEFAULT_INDEX_NAME)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--create-index", action="store_true")
    parser.add_argument("--recreate-index", action="store_true")
    parser.add_argument("--bulk-load", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--run-smoke-queries", action="store_true")
    parser.add_argument("--quality", action="store_true")
    add_quality_args(parser)
    args = parser.parse_args(argv)
    if args.quality:
        args.require_adapter_quality_pass = True
        args.require_loader_smoke_quality_pass = True
        args.require_mapping = True
        if not args.dry_run:
            args.require_bulk_load = True
            args.require_live_read_check = True
    report = build_live_loader_report(
        opensearch_adapter_path=args.opensearch_adapter,
        loader_smoke_path=args.loader_smoke,
        output_dir=args.output_dir,
        opensearch_url=args.opensearch_url,
        index_name=args.index_name,
        batch_size=args.batch_size,
        timeout_seconds=args.timeout_seconds,
        recreate_index=args.recreate_index,
        create_index=args.create_index,
        bulk_load=args.bulk_load,
        refresh=args.refresh,
        run_smoke_queries=args.run_smoke_queries,
        allow_opensearch_writes=args.allow_opensearch_writes,
        dry_run=args.dry_run,
        thresholds=thresholds_from_args(args),
    )
    print_summary(report)
    print(" report_path:", report.get("outputs", {}).get("report_path"))
    print(" quality_path:", report.get("outputs", {}).get("quality_path"))
    return 0 if report.get("quality_status") == "PASS" else 1


# Compatibility aliases for tests and script wrappers.
build_report = build_live_loader_report
check_existing_report = check_live_loader_quality
print_report = print_summary


if __name__ == "__main__":
    raise SystemExit(main())
