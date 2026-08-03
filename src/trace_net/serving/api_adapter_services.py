"""Adapter-backed service layer for the TIFF FastAPI boundary.

The public FastAPI route contract should not know whether storage comes from
local JSON/SQLite artifacts or production PostgreSQL/OpenSearch/Qdrant.  This
module is the seam: it calls storage adapters and normalizes responses into the
same JSON shapes the existing UI expects.
"""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from tiff.storage_adapters import StoreBundle, create_local_store_bundle


@dataclass
class AskResult:
    question: str
    answer_text: str
    returncode: int
    elapsed_seconds: float
    llm_used: bool
    embeddings_used: bool
    command: list[str]
    stderr_preview: str = ""

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer_text": self.answer_text,
            "returncode": self.returncode,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "llm_used": self.llm_used,
            "embeddings_used": self.embeddings_used,
            "command": self.command,
            "stderr_preview": self.stderr_preview,
        }


@dataclass
class TiffApiServices:
    stores: StoreBundle
    repo_root: Path = Path(".")

    def api_status(self) -> dict[str, Any]:
        quality = self.stores.quality.status()
        q_gate = _as_dict(quality.get("quality_gate"))
        graph_quality = _as_dict(quality.get("graph_quality"))
        q_summary = _as_dict(q_gate.get("summary"))
        g_summary = _as_dict(graph_quality.get("summary", graph_quality))
        status = q_gate.get("status") or quality.get("status") or _as_dict(quality.get("manifest")).get("status") or "unknown"
        return {
            "status": status,
            "pipeline_status": q_summary.get("pipeline_status", _as_dict(quality.get("manifest")).get("pipeline_status", "unknown")),
            "graph_quality_status": graph_quality.get("status", "unknown"),
            "storage_mode": "adapter",
            "graph": {
                "present": bool(g_summary.get("graph_present", False)),
                "nodes_total": g_summary.get("nodes_total"),
                "edges_total": g_summary.get("edges_total"),
                "page_nodes": g_summary.get("page_nodes"),
                "page_context_nodes": g_summary.get("page_context_nodes"),
                "source_link_nodes": g_summary.get("source_link_nodes"),
                "pages_without_context": g_summary.get("pages_without_context"),
                "pages_without_source_links": g_summary.get("pages_without_source_links"),
            },
            "query_tests": {
                "user_query_present": bool(g_summary.get("user_query_results_present")),
                "user_query_total": g_summary.get("user_query_total"),
                "user_query_fail": g_summary.get("user_query_fail"),
                "realistic_present": bool(g_summary.get("realistic_query_results_present")),
                "realistic_total": g_summary.get("realistic_query_total"),
                "realistic_fail": g_summary.get("realistic_query_fail"),
            },
        }

    def organization_summary(self) -> dict[str, Any]:
        return self.stores.catalog.organization_summary()

    def part_lookup(self, part_number: str, *, limit: int = 8) -> dict[str, Any]:
        raw = self.stores.catalog.get_part(part_number, limit=limit)
        if raw.get("status") != "ok":
            return raw
        pages = [_normalize_page_item(item) for item in _as_list(raw.get("pages"))]
        return {
            "status": "ok",
            "part_number": raw.get("part_number", part_number),
            "part_node": raw.get("node") or raw.get("raw"),
            "nomenclature": raw.get("nomenclature"),
            "pages_total": raw.get("pages_count") or raw.get("page_count") or raw.get("mentions") or len(pages),
            "pages": pages,
            "raw": raw,
        }

    def page_lookup(self, page_id: str, *, limit: int = 8) -> dict[str, Any]:
        raw = self.stores.catalog.get_page(page_id)
        if raw.get("status") != "ok":
            return raw
        page = _normalize_page_payload(raw, page_id=page_id)
        parts = [_normalize_part_item(part) for part in _as_list(raw.get("parts"))[:limit]]
        return {"status": "ok", "page": page, "parts": parts, "raw": raw}

    def ata_lookup(self, ata_code: str, *, limit: int = 12) -> dict[str, Any]:
        raw = self.stores.catalog.get_ata(ata_code, limit=limit)
        if raw.get("status") != "ok":
            return raw
        return {
            "status": "ok",
            "ata": {"label": raw.get("ata_code") or ata_code, "manual": raw.get("manual")},
            "pages_total": raw.get("pages_count") or raw.get("page_count") or len(_as_list(raw.get("pages"))),
            "pages": [_normalize_page_item(item) for item in _as_list(raw.get("pages"))[:limit]],
            "raw": raw,
        }

    def trace_part(self, part_number: str, *, limit: int = 8) -> dict[str, Any]:
        if self.stores.trace is not None:
            return self.stores.trace.trace_part(part_number, limit=limit)
        return self.part_lookup(part_number, limit=limit)

    def trace_page(self, page_id: str, *, limit: int = 8) -> dict[str, Any]:
        if self.stores.trace is not None:
            return self.stores.trace.trace_page(page_id, limit=limit)
        return self.page_lookup(page_id, limit=limit)

    def trace_vector_payload(self, page_id: str, *, chunk_id: str | None = None, score: float | None = None, limit: int = 8) -> dict[str, Any]:
        if self.stores.trace is not None:
            return self.stores.trace.trace_vector_payload(page_id=page_id, chunk_id=chunk_id, score=score or 0.0, limit=limit)
        return self.stores.vector.trace_payload(page_id=page_id, chunk_id=chunk_id, score=score or 0.0)

    def ask_question(self, question: str, *, config: str = "local_config.yaml", timeout_seconds: int = 240) -> AskResult:
        # The ask path still delegates to the current RAG entrypoint.  It is
        # isolated here so a future AnswerStore can replace it without changing
        # the FastAPI route contract.
        command = [sys.executable, "scripts/operations/ingestion/ask_tiff_rag.py", "--config", config, question]
        start = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        elapsed = time.perf_counter() - start
        stdout = completed.stdout or ""
        return AskResult(
            question=question,
            answer_text=stdout,
            returncode=completed.returncode,
            elapsed_seconds=elapsed,
            llm_used="LLM used: True" in stdout,
            embeddings_used="Embeddings used: True" in stdout,
            command=command,
            stderr_preview=_preview(completed.stderr or ""),
        )

    def submit_feedback(
        self,
        *,
        question: str,
        rating: str,
        category: str,
        reason: str,
        answer_text: str | None = None,
        answer_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.stores.feedback.save_feedback({
            "question": question,
            "rating": rating,
            "category": category,
            "reason": reason,
            "answer_text": answer_text,
            "answer_id": answer_id,
            "metadata": dict(metadata or {}),
        })

    def summarize_feedback(self) -> dict[str, Any]:
        return self.stores.feedback.summary()


_default_services: TiffApiServices | None = None


def create_services(repo_root: str | Path = Path(".")) -> TiffApiServices:
    return TiffApiServices(stores=create_local_store_bundle(Path(repo_root)), repo_root=Path(repo_root))


def get_default_services() -> TiffApiServices:
    global _default_services
    if _default_services is None:
        _default_services = create_services()
    return _default_services


# Function-style wrappers keep existing imports/tests simple while routing all
# route logic through the adapter-backed service.
def api_status() -> dict[str, Any]:
    return get_default_services().api_status()


def organization_summary() -> dict[str, Any]:
    return get_default_services().organization_summary()


def part_lookup(part_number: str, *, limit: int = 8) -> dict[str, Any]:
    return get_default_services().part_lookup(part_number, limit=limit)


def page_lookup(page_id: str, *, limit: int = 8) -> dict[str, Any]:
    return get_default_services().page_lookup(page_id, limit=limit)


def ata_lookup(ata_code: str, *, limit: int = 12) -> dict[str, Any]:
    return get_default_services().ata_lookup(ata_code, limit=limit)


def trace_part(part_number: str, *, limit: int = 8) -> dict[str, Any]:
    return get_default_services().trace_part(part_number, limit=limit)


def trace_page(page_id: str, *, limit: int = 8) -> dict[str, Any]:
    return get_default_services().trace_page(page_id, limit=limit)


def trace_vector_payload(page_id: str, *, chunk_id: str | None = None, score: float | None = None, limit: int = 8) -> dict[str, Any]:
    return get_default_services().trace_vector_payload(page_id, chunk_id=chunk_id, score=score, limit=limit)


def ask_question(question: str, *, config: str = "local_config.yaml", timeout_seconds: int = 240) -> AskResult:
    return get_default_services().ask_question(question, config=config, timeout_seconds=timeout_seconds)


def submit_feedback(
    *,
    question: str,
    rating: str,
    category: str,
    reason: str,
    answer_text: str | None = None,
    answer_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return get_default_services().submit_feedback(
        question=question,
        rating=rating,
        category=category,
        reason=reason,
        answer_text=answer_text,
        answer_id=answer_id,
        metadata=metadata,
    )


def summarize_feedback() -> dict[str, Any]:
    return get_default_services().summarize_feedback()


def _normalize_page_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"page_id": str(item), "raw": item}
    page = _as_dict(item.get("page")) or item
    source = _as_dict(item.get("source"))
    context = _as_dict(item.get("context"))
    page_id = item.get("page_id") or page.get("page_id") or page.get("id")
    return _normalize_page_payload({"page": page, "source": source, "context": context}, page_id=str(page_id or ""))


def _normalize_page_payload(raw: Mapping[str, Any], *, page_id: str) -> dict[str, Any]:
    page = _as_dict(raw.get("page"))
    source = _as_dict(raw.get("source"))
    context = _as_dict(raw.get("context"))
    source_url = _first_nonempty(source, "source_url", "rescarta_url", "url") or _first_nonempty(page, "source_url", "rescarta_url", "source")
    context_summary = _first_nonempty(context, "summary", "short_summary", "context", "text")
    return {
        "page_id": _first_nonempty(page, "page_id", "id") or page_id,
        "node": page,
        "label": _first_nonempty(page, "page_label", "label") or page_id,
        "document": _first_nonempty(page, "manual", "manual_title", "document", "document_title"),
        "ata": _first_nonempty(page, "ata", "ata_code"),
        "source_link_present": bool(source_url),
        "source_link": source,
        "context_present": bool(context),
        "context_score": _context_score(context),
        "context_summary": context_summary,
    }


def _normalize_part_item(part: Any) -> dict[str, Any]:
    if not isinstance(part, dict):
        return {"part_number": str(part)}
    return {
        "part_number": _first_nonempty(part, "part_number", "part", "label", "id"),
        "nomenclature": _first_nonempty(part, "nomenclature", "name"),
        "raw": part,
    }


def _context_score(context: Mapping[str, Any]) -> float:
    if not context:
        return 0.0
    raw_score = context.get("score") or context.get("context_score")
    try:
        if raw_score is not None:
            return float(raw_score)
    except Exception:
        pass
    confidence = str(context.get("confidence", "")).lower()
    return {"high": 0.9, "medium": 0.65, "low": 0.35}.get(confidence, 0.5)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_nonempty(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _preview(text: str, limit: int = 1200) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."
