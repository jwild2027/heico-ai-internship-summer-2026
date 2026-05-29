"""Adapter-backed API helper functions for the TIFF RAG service.

The FastAPI routes call this module instead of reaching directly into local
JSON files/scripts.  Today the default store bundle is local artifacts; later,
the same route helpers can receive PostgreSQL/OpenSearch/Qdrant/ResCarta-backed
store implementations.
"""

from __future__ import annotations

import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from tiff.storage_adapters import StoreBundle, build_local_store_bundle

JsonDict = dict[str, Any]


@lru_cache(maxsize=8)
def get_store_bundle(config_path: str = "local_config.yaml") -> StoreBundle:
    """Return the active store bundle for API requests.

    The cache keeps route handlers lightweight while preserving a clean seam for
    future dependency injection/testing.  Tests may monkeypatch this function or
    call the helpers with an explicit bundle.
    """

    return build_local_store_bundle(repo_root=Path.cwd(), config_path=config_path)


def status_from_store(bundle: StoreBundle | None = None) -> JsonDict:
    bundle = bundle or get_store_bundle()
    quality_status = bundle.quality.status()
    graph_quality = _as_mapping(quality_status.get("graph_quality"))
    graph_summary = _summary(graph_quality)
    quality = _as_mapping(quality_status.get("quality"))

    status = str(quality_status.get("status") or quality.get("status") or "unknown").lower()
    return {
        "status": status,
        "mode": bundle.mode,
        "stores": {
            "catalog": type(bundle.catalog).__name__,
            "trace": type(bundle.trace).__name__,
            "answers": type(bundle.answers).__name__,
            "feedback": type(bundle.feedback).__name__,
            "quality": type(bundle.quality).__name__,
            "keyword": type(bundle.keyword).__name__ if bundle.keyword else None,
            "vector": type(bundle.vector).__name__ if bundle.vector else None,
            "source": type(bundle.source).__name__ if bundle.source else None,
        },
        "graph": {
            "nodes_total": _int_value(graph_summary, "nodes_total", "nodes", default=0),
            "edges_total": _int_value(graph_summary, "edges_total", "edges", default=0),
            "page_nodes": _int_value(graph_summary, "page_nodes", "pages", default=0),
            "page_context_nodes": _int_value(graph_summary, "page_context_nodes", "contexts", default=0),
            "source_link_nodes": _int_value(graph_summary, "source_link_nodes", "source_links", default=0),
            "pages_without_context": _int_value(graph_summary, "pages_without_context", default=0),
            "pages_without_source_links": _int_value(graph_summary, "pages_without_source_links", default=0),
        },
        "quality": quality_status,
    }


def organization_summary_from_store(bundle: StoreBundle | None = None) -> JsonDict:
    bundle = bundle or get_store_bundle()
    summary = bundle.catalog.organization_summary()
    out = dict(summary or {})
    out.setdefault("status", "ok" if summary else "missing")
    out.setdefault("mode", bundle.mode)
    return out


def part_lookup_from_store(part_number: str, *, limit: int = 8, bundle: StoreBundle | None = None) -> JsonDict:
    bundle = bundle or get_store_bundle()
    part = bundle.catalog.get_part(part_number)
    if not part:
        return {"status": "not_found", "part_number": part_number, "pages": [], "pages_total": 0}

    pages = _extract_page_refs(part)[:limit]
    pages_total = _page_count(part, fallback=len(_extract_page_refs(part)))
    trace = _unwrap_trace(bundle.trace.trace_part(part_number, limit=limit))
    trace_summary = _as_mapping(trace.get("summary"))
    if trace_summary.get("total_pages_found") is not None:
        pages_total = int(trace_summary.get("total_pages_found") or pages_total or 0)

    return {
        "status": "ok",
        "part_number": _part_number(part) or part_number,
        "nomenclature": _nomenclature(part),
        "pages_total": pages_total,
        "pages": pages,
        "part": part,
        "trace": trace,
    }


def page_lookup_from_store(page_id: str, *, limit: int = 8, bundle: StoreBundle | None = None) -> JsonDict:
    bundle = bundle or get_store_bundle()
    page = bundle.catalog.get_page(page_id)
    if not page:
        return {"status": "not_found", "page_id": page_id}

    source = bundle.source.resolve_page(page_id) if bundle.source else None
    trace = _unwrap_trace(bundle.trace.trace_page(page_id, limit=limit))
    trace_summary = _as_mapping(trace.get("summary"))
    page_summary = {
        "page_id": _page_id(page) or page_id,
        "label": _first(page, "page_label", "label", "page"),
        "ata": _first(page, "ata_code", "ata"),
        "document": _first(page, "manual", "document", "document_title", "title"),
        "source_link_present": bool(source and _first(source, "source_url", "tiff_path", "ocr_path"))
        or bool(trace_summary.get("source_link_present")),
        "context_present": bool(trace_summary.get("context_present")) or bool(_first(page, "context", "page_context", "summary")),
        "context_score": float(trace_summary.get("context_score") or 0.0),
        "source": source,
        "record": page,
    }
    return {"status": "ok", "page_id": page_id, "page": page_summary, "trace": trace}


def ata_lookup_from_store(ata_code: str, *, limit: int = 12, bundle: StoreBundle | None = None) -> JsonDict:
    bundle = bundle or get_store_bundle()
    ata = bundle.catalog.get_ata(ata_code)
    if not ata:
        return {"status": "not_found", "ata_code": ata_code}
    pages = _extract_page_refs(ata)[:limit]
    page_count = _page_count(ata, fallback=len(_extract_page_refs(ata)))
    return {"status": "ok", "ata_code": _first(ata, "ata_code", "ata", "code") or ata_code, "pages_total": page_count, "pages": pages, "ata": ata}


def trace_part_from_store(part_number: str, *, limit: int = 8, bundle: StoreBundle | None = None) -> JsonDict:
    bundle = bundle or get_store_bundle()
    return _unwrap_trace(bundle.trace.trace_part(part_number, limit=limit))


def trace_page_from_store(page_id: str, *, limit: int = 8, bundle: StoreBundle | None = None) -> JsonDict:
    bundle = bundle or get_store_bundle()
    return _unwrap_trace(bundle.trace.trace_page(page_id, limit=limit))


def trace_vector_payload_from_store(
    *,
    page_id: str,
    chunk_id: str | None = None,
    score: float | None = None,
    limit: int = 8,
    bundle: StoreBundle | None = None,
) -> JsonDict:
    bundle = bundle or get_store_bundle()
    trace = _unwrap_trace(bundle.trace.trace_vector_payload(page_id, chunk_id=chunk_id or "", score=float(score or 0.0)))
    trace.setdefault("vector_payload", {"page_id": page_id, "chunk_id": chunk_id, "score": score, "limit": limit})
    return trace


def ask_from_store(question: str, *, config: str = "local_config.yaml", timeout_seconds: int = 240, bundle: StoreBundle | None = None) -> JsonDict:
    bundle = bundle or get_store_bundle(config)
    result = dict(bundle.answers.ask(question, timeout_seconds=timeout_seconds))
    result.setdefault("status", "ok" if result.get("returncode") == 0 else "failed")
    result.setdefault("question", question)
    return result


def submit_feedback_from_store(
    *,
    question: str,
    rating: str,
    category: str = "other",
    reason: str = "",
    answer_id: str | None = None,
    answer_text: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    bundle: StoreBundle | None = None,
) -> JsonDict:
    bundle = bundle or get_store_bundle()
    record: JsonDict = {
        "feedback_id": f"fb_{uuid.uuid4().hex}",
        "created_at_epoch": time.time(),
        "question": question,
        "rating": rating,
        "category": category,
        "reason": reason,
        "answer_id": answer_id,
        "answer_text": answer_text,
        "metadata": dict(metadata or {}),
    }
    return bundle.feedback.submit_feedback(record)


def feedback_summary_from_store(bundle: StoreBundle | None = None) -> JsonDict:
    bundle = bundle or get_store_bundle()
    return bundle.feedback.feedback_summary()


def _unwrap_trace(raw: JsonDict) -> JsonDict:
    report = raw.get("report")
    if isinstance(report, dict) and report:
        out = dict(report)
        out.setdefault("command_status", raw.get("status"))
        out.setdefault("returncode", raw.get("returncode"))
        out.setdefault("elapsed_seconds", raw.get("elapsed_seconds"))
        return out
    return raw


def _summary(data: Mapping[str, Any]) -> Mapping[str, Any]:
    value = data.get("summary")
    return value if isinstance(value, Mapping) else data


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int_value(data: Mapping[str, Any], *keys: str, default: int = 0) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return default


def _first(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
        props = record.get("properties")
        if isinstance(props, Mapping) and props.get(key) not in (None, ""):
            return props.get(key)
        data = record.get("data")
        if isinstance(data, Mapping) and data.get(key) not in (None, ""):
            return data.get(key)
    return None


def _part_number(record: Mapping[str, Any]) -> str | None:
    value = _first(record, "part_number", "part", "number", "id", "label")
    if not isinstance(value, str):
        return None
    if value.startswith("part:"):
        value = value.split(":", 1)[1].replace("_", "-")
    return value


def _page_id(record: Mapping[str, Any]) -> str | None:
    value = _first(record, "page_id", "id", "page", "node_id")
    if not isinstance(value, str):
        return None
    if value.startswith("page:"):
        value = value.split(":", 1)[1]
    return value


def _nomenclature(record: Mapping[str, Any]) -> str | None:
    value = _first(record, "nomenclature", "name", "title", "label")
    return str(value) if value not in (None, "") else None


def _page_count(record: Mapping[str, Any], *, fallback: int = 0) -> int:
    for key in ("pages", "page_count", "pages_total", "mentions", "mention_count"):
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, list):
            return len(value)
    return fallback


def _extract_page_refs(record: Mapping[str, Any]) -> list[JsonDict]:
    for key in ("pages", "page_refs", "appearances", "source_pages"):
        value = record.get(key)
        if isinstance(value, list):
            return [item if isinstance(item, dict) else {"page_id": str(item)} for item in value]
    return []
