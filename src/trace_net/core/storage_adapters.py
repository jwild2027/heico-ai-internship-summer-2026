"""Storage adapter interfaces and local implementations for the TIFF backend.

This module is intentionally thin.  It gives the API and UI a stable boundary now,
while the project is still backed by JSON/SQLite artifacts, and leaves clear seams
for PostgreSQL, OpenSearch, Qdrant, and ResCarta-backed implementations later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence

JsonDict = Dict[str, Any]


# ---------------------------------------------------------------------------
# Interface contracts
# ---------------------------------------------------------------------------

class CatalogStore(Protocol):
    """Structured graph/catalog lookup interface.

    Future production implementation: PostgreSQL.
    Current local implementation: organization export JSON + graph JSON.
    """

    def organization_summary(self) -> JsonDict: ...
    def get_part(self, part_number: str, *, limit: int = 10) -> JsonDict: ...
    def get_page(self, page_id: str) -> JsonDict: ...
    def get_ata(self, ata_code: str, *, limit: int = 20) -> JsonDict: ...


class KeywordSearchStore(Protocol):
    """Exact keyword/OCR search interface.

    Future production implementation: OpenSearch.
    Current local implementation: lightweight JSON/page-context search.
    """

    def search(self, query: str, *, limit: int = 10) -> JsonDict: ...


class VectorStore(Protocol):
    """Semantic/vector retrieval interface.

    Future production implementation: Qdrant.
    Current local implementation: simulated vector payload trace using page_id.
    """

    def trace_payload(self, *, page_id: str, chunk_id: Optional[str] = None, score: float = 0.0) -> JsonDict: ...


class TraceStore(Protocol):
    """Graph traceability interface.

    Future production implementation: PostgreSQL graph traversal.
    Current local implementation: graph JSON traceability helpers.
    """

    def trace_part(self, part_number: str, *, limit: int = 8) -> JsonDict: ...
    def trace_page(self, page_id: str, *, limit: int = 8) -> JsonDict: ...
    def trace_vector_payload(self, *, page_id: str, chunk_id: Optional[str] = None, score: float = 0.0, limit: int = 8) -> JsonDict: ...


class SourceStore(Protocol):
    """Source-link/source-file resolution interface.

    Future production implementation: ResCarta/source-link service.
    Current local implementation: source fields from page/graph JSON.
    """

    def get_page_source(self, page_id: str) -> JsonDict: ...


class FeedbackStore(Protocol):
    """User feedback write/read interface.

    Future production implementation: PostgreSQL feedback tables.
    Current local implementation: JSONL + summary JSON.
    """

    def save_feedback(self, feedback: Mapping[str, Any]) -> JsonDict: ...
    def summary(self) -> JsonDict: ...


class QualityStore(Protocol):
    """Pipeline and graph quality status interface.

    Future production implementation: PostgreSQL/run status service.
    Current local implementation: latest JSON artifacts.
    """

    def status(self) -> JsonDict: ...


# ---------------------------------------------------------------------------
# Dataclass bundle used by API/server wiring
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StoreBundle:
    catalog: CatalogStore
    keyword_search: KeywordSearchStore
    vector: VectorStore
    source: SourceStore
    feedback: FeedbackStore
    quality: QualityStore
    trace: Optional[TraceStore] = None
    mode: str = "local_artifacts"


# ---------------------------------------------------------------------------
# Local JSON-backed stores
# ---------------------------------------------------------------------------

@dataclass
class LocalArtifactPaths:
    """Default artifact paths for the local MVP backend."""

    repo_root: Path = Path(".")
    organization_export_dir: Path = Path("local_data/organization/export")
    graph_dir: Path = Path("local_data/organization/graph")
    context_file: Path = Path("local_data/organization/context/page_contexts.json")
    quality_gate_file: Path = Path("local_data/pipeline_runs/latest_quality_gate.json")
    manifest_file: Path = Path("local_data/pipeline_runs/latest_backend_pipeline.json")
    feedback_jsonl: Path = Path("local_data/feedback/user_feedback.jsonl")
    feedback_summary: Path = Path("local_data/feedback/user_feedback_summary.json")

    def resolve(self) -> "LocalArtifactPaths":
        root = self.repo_root
        return LocalArtifactPaths(
            repo_root=root,
            organization_export_dir=_resolve(root, self.organization_export_dir),
            graph_dir=_resolve(root, self.graph_dir),
            context_file=_resolve(root, self.context_file),
            quality_gate_file=_resolve(root, self.quality_gate_file),
            manifest_file=_resolve(root, self.manifest_file),
            feedback_jsonl=_resolve(root, self.feedback_jsonl),
            feedback_summary=_resolve(root, self.feedback_summary),
        )


def create_local_store_bundle(repo_root: Path | str = Path(".")) -> StoreBundle:
    """Create the local MVP store bundle.

    This is the function the API can call today.  Later, a production factory can
    return PostgreSQL/OpenSearch/Qdrant/ResCarta-backed stores with the same
    interface shape.
    """

    paths = LocalArtifactPaths(repo_root=Path(repo_root)).resolve()
    catalog = LocalCatalogStore(paths)
    return StoreBundle(
        catalog=catalog,
        keyword_search=LocalKeywordSearchStore(paths, catalog),
        vector=LocalVectorStore(paths, catalog),
        source=LocalSourceStore(catalog),
        feedback=LocalFeedbackStore(paths),
        quality=LocalQualityStore(paths),
        trace=LocalTraceStore(paths),
    )


@dataclass
class LocalCatalogStore:
    paths: LocalArtifactPaths
    _page_index: Optional[JsonDict] = field(default=None, init=False, repr=False)
    _part_tree: Optional[JsonDict] = field(default=None, init=False, repr=False)
    _ata_tree: Optional[JsonDict] = field(default=None, init=False, repr=False)
    _manual_ata_tree: Optional[JsonDict] = field(default=None, init=False, repr=False)
    _summary: Optional[JsonDict] = field(default=None, init=False, repr=False)
    _graph_nodes: Optional[List[JsonDict]] = field(default=None, init=False, repr=False)
    _graph_edges: Optional[List[JsonDict]] = field(default=None, init=False, repr=False)
    _contexts: Optional[List[JsonDict]] = field(default=None, init=False, repr=False)

    def organization_summary(self) -> JsonDict:
        summary = self._load_summary()
        return {
            "status": "ok" if bool(summary) else "missing",
            "summary": summary,
            "paths": {
                "organization_export_dir": str(self.paths.organization_export_dir),
                "graph_dir": str(self.paths.graph_dir),
            },
        }

    def get_part(self, part_number: str, *, limit: int = 10) -> JsonDict:
        normalized = _normalize_part(part_number)
        part = self._find_part(part_number)
        if part is None:
            return {"status": "not_found", "part_number": part_number, "normalized": normalized, "pages": []}

        pages = _extract_list(part, "pages", "page_refs", "source_pages", "appearances")
        page_results: List[JsonDict] = []
        for page_ref in pages[:limit]:
            page_id = _value_from_ref(page_ref, "page_id", "id")
            page = self._find_page(str(page_id)) if page_id else None
            source = self._page_source_from_page(page or page_ref)
            context = self._page_context(str(page_id)) if page_id else None
            page_results.append({
                "page_id": page_id,
                "page": page or page_ref,
                "source": source,
                "context": context,
            })

        return {
            "status": "ok",
            "part_number": part.get("part_number") or part.get("id") or part_number,
            "normalized": normalized,
            "nomenclature": _first_nonempty(part, "nomenclature", "name", "label"),
            "mentions": part.get("mentions") or part.get("mention_count"),
            "pages_count": part.get("pages_count") or part.get("page_count") or len(pages),
            "pages": page_results,
            "raw": part,
        }

    def get_page(self, page_id: str) -> JsonDict:
        page = self._find_page(page_id)
        if page is None:
            return {"status": "not_found", "page_id": page_id}
        return {
            "status": "ok",
            "page_id": _first_nonempty(page, "page_id", "id") or page_id,
            "page": page,
            "source": self._page_source_from_page(page),
            "context": self._page_context(page_id),
            "parts": self._page_parts(page_id),
        }

    def get_ata(self, ata_code: str, *, limit: int = 20) -> JsonDict:
        ata = self._find_ata(ata_code)
        if ata is None:
            return {"status": "not_found", "ata_code": ata_code, "pages": []}

        pages = _extract_list(ata, "pages", "page_refs", "source_pages")
        page_results: List[JsonDict] = []
        for ref in pages[:limit]:
            page_id = _value_from_ref(ref, "page_id", "id")
            page = self._find_page(str(page_id)) if page_id else None
            page_results.append({
                "page_id": page_id,
                "page": page or ref,
                "source": self._page_source_from_page(page or ref),
                "context": self._page_context(str(page_id)) if page_id else None,
            })

        return {
            "status": "ok",
            "ata_code": ata.get("ata_code") or ata.get("ata") or ata_code,
            "manual": _first_nonempty(ata, "manual", "manual_title", "document", "document_title"),
            "pages_count": ata.get("pages_count") or ata.get("page_count") or len(pages),
            "parts_count": ata.get("parts_count") or ata.get("part_count"),
            "pages": page_results,
            "raw": ata,
        }

    def graph_trace_page(self, page_id: str) -> JsonDict:
        page_result = self.get_page(page_id)
        if page_result.get("status") != "ok":
            return page_result
        page = page_result["page"]
        return {
            "status": "ok",
            "page_id": page_id,
            "document": _first_nonempty(page, "manual", "manual_title", "document", "document_title"),
            "ata": _first_nonempty(page, "ata", "ata_code"),
            "source_link_present": bool(page_result.get("source", {}).get("source_url") or page_result.get("source", {}).get("rescarta_url")),
            "context_present": bool(page_result.get("context")),
            "context": page_result.get("context"),
            "parts_sample": page_result.get("parts", [])[:10],
        }

    # ----- internal loaders -----

    def _load_page_index(self) -> JsonDict:
        if self._page_index is None:
            self._page_index = _load_json(self.paths.organization_export_dir / "page_index.json", default={})
        return self._page_index

    def _load_part_tree(self) -> JsonDict:
        if self._part_tree is None:
            self._part_tree = _load_json(self.paths.organization_export_dir / "part_tree.json", default={})
        return self._part_tree

    def _load_ata_tree(self) -> JsonDict:
        if self._ata_tree is None:
            self._ata_tree = _load_json(self.paths.organization_export_dir / "ata_tree.json", default={})
        return self._ata_tree

    def _load_manual_ata_tree(self) -> JsonDict:
        if self._manual_ata_tree is None:
            self._manual_ata_tree = _load_json(self.paths.organization_export_dir / "manual_ata_tree.json", default={})
        return self._manual_ata_tree

    def _load_summary(self) -> JsonDict:
        if self._summary is None:
            self._summary = _load_json(self.paths.organization_export_dir / "organization_summary.json", default={})
        return self._summary

    def _load_nodes(self) -> List[JsonDict]:
        if self._graph_nodes is None:
            data = _load_json(self.paths.graph_dir / "graph_nodes.json", default=[])
            self._graph_nodes = data if isinstance(data, list) else data.get("nodes", [])
        return self._graph_nodes

    def _load_edges(self) -> List[JsonDict]:
        if self._graph_edges is None:
            data = _load_json(self.paths.graph_dir / "graph_edges.json", default=[])
            self._graph_edges = data if isinstance(data, list) else data.get("edges", [])
        return self._graph_edges

    def _load_contexts(self) -> List[JsonDict]:
        if self._contexts is None:
            data = _load_json(self.paths.context_file, default=[])
            self._contexts = data if isinstance(data, list) else data.get("contexts", [])
        return self._contexts

    # ----- internal finders -----

    def _find_part(self, part_number: str) -> Optional[JsonDict]:
        normalized = _normalize_part(part_number)
        for part in _iter_collection(self._load_part_tree(), "parts", "items", "part_tree"):
            candidates = [part.get("part_number"), part.get("part"), part.get("id"), part.get("label")]
            if any(_normalize_part(str(c)) == normalized for c in candidates if c):
                return part
        # Fallback to graph nodes.
        for node in self._load_nodes():
            if _node_type(node) == "part":
                candidates = [node.get("part_number"), node.get("label"), node.get("id")]
                if any(_normalize_part(str(c)) == normalized for c in candidates if c):
                    return node
        return None

    def _find_page(self, page_id: str) -> Optional[JsonDict]:
        page_id = _strip_graph_prefix(page_id, "page")
        for page in _iter_collection(self._load_page_index(), "pages", "items", "page_index"):
            if str(page.get("page_id") or page.get("id")) == page_id:
                return page
        # Fallback to graph nodes.
        graph_id = f"page:{page_id}"
        for node in self._load_nodes():
            if node.get("id") == graph_id or node.get("page_id") == page_id:
                return node
        return None

    def _find_ata(self, ata_code: str) -> Optional[JsonDict]:
        wanted = _norm_text(ata_code)
        for ata in _iter_collection(self._load_ata_tree(), "ata_sections", "ata", "items", "sections"):
            candidates = [ata.get("ata_code"), ata.get("ata"), ata.get("label"), ata.get("id")]
            if any(wanted in _norm_text(str(c)) or _norm_text(str(c)) == wanted for c in candidates if c):
                return ata
        # Fallback: manual tree may contain nested ATA entries.
        for entry in _walk_json_dicts(self._load_manual_ata_tree()):
            candidates = [entry.get("ata_code"), entry.get("ata"), entry.get("label")]
            if any(_norm_text(str(c)) == wanted for c in candidates if c):
                return entry
        return None

    def _page_context(self, page_id: str) -> Optional[JsonDict]:
        page_id = _strip_graph_prefix(page_id, "page")
        graph_context_id = f"page_context:{page_id}"
        for ctx in self._load_contexts():
            if str(ctx.get("page_id") or ctx.get("id")) in {page_id, graph_context_id}:
                return ctx
        for node in self._load_nodes():
            if node.get("id") == graph_context_id or node.get("page_id") == page_id:
                return node
        return None

    def _page_parts(self, page_id: str) -> List[JsonDict]:
        page_graph_id = f"page:{_strip_graph_prefix(page_id, 'page')}"
        part_ids: List[str] = []
        for edge in self._load_edges():
            edge_type = edge.get("type") or edge.get("edge_type") or edge.get("label")
            src = edge.get("source") or edge.get("from") or edge.get("source_id")
            dst = edge.get("target") or edge.get("to") or edge.get("target_id")
            if edge_type == "MENTIONS_PART" and src == page_graph_id and dst:
                part_ids.append(str(dst))
        out: List[JsonDict] = []
        for pid in part_ids[:50]:
            part = self._find_part(pid.replace("part:", ""))
            if part:
                out.append(part)
        return out

    def _page_source_from_page(self, page: Mapping[str, Any]) -> JsonDict:

        # compatibility: allow page-id strings when resolving page source
        # Some ATA tree/page references are stored as page_id strings instead
        # of full page dictionaries. Resolve those through get_page() before
        # reading source_url/rescarta_url/tiff/ocr fields.
        if page is None:
            return None
        if not isinstance(page, Mapping):
            page_id = str(page)
            resolved = None
            try:
                resolved = self.get_page(page_id)
            except Exception:
                resolved = None
            if isinstance(resolved, Mapping):
                # Some stores return the page fields directly; others wrap the
                # page under a `page` key. Support both shapes.
                nested_page = resolved.get("page")
                if isinstance(nested_page, Mapping):
                    page = nested_page
                else:
                    page = resolved
            else:
                return {"page_id": page_id}
        return {
            "source_url": _first_nonempty(page, "source_url", "rescarta_url", "source"),
            "rescarta_url": _first_nonempty(page, "rescarta_url", "source_url", "source"),
            "tiff_path": _first_nonempty(page, "tiff_path", "source_image_path", "image_path", "tiff"),
            "ocr_path": _first_nonempty(page, "ocr_path", "ocr_text_path", "ocr"),
        }


@dataclass
class LocalKeywordSearchStore:
    paths: LocalArtifactPaths
    catalog: LocalCatalogStore

    def search(self, query: str, *, limit: int = 10) -> JsonDict:
        query_norm = _norm_text(query)
        hits: List[JsonDict] = []
        if not query_norm:
            return {"status": "ok", "query": query, "hits": []}
        # Lightweight local search over AI context summaries/topics. Future: OpenSearch.
        for ctx in self.catalog._load_contexts():
            text = " ".join(str(x) for x in [
                ctx.get("page_id"),
                ctx.get("summary"),
                ctx.get("short_summary"),
                " ".join(ctx.get("topics", []) if isinstance(ctx.get("topics"), list) else []),
                " ".join(ctx.get("important_parts", []) if isinstance(ctx.get("important_parts"), list) else []),
            ])
            text_norm = _norm_text(text)
            if query_norm in text_norm:
                page_id = str(ctx.get("page_id") or "")
                hits.append({
                    "page_id": page_id,
                    "score": 1.0,
                    "context": ctx,
                    "page": self.catalog.get_page(page_id) if page_id else None,
                })
                if len(hits) >= limit:
                    break
        return {"status": "ok", "query": query, "backend": "local_context_scan", "hits": hits}


@dataclass
class LocalVectorStore:
    paths: LocalArtifactPaths
    catalog: LocalCatalogStore

    def trace_payload(self, *, page_id: str, chunk_id: Optional[str] = None, score: float = 0.0) -> JsonDict:
        page_trace = self.catalog.graph_trace_page(page_id)
        return {
            "status": page_trace.get("status", "unknown"),
            "backend": "local_simulated_qdrant_payload",
            "vector_payload": {
                "page_id": page_id,
                "chunk_id": chunk_id,
                "score": score,
            },
            "graph_trace": page_trace,
        }


@dataclass
class LocalTraceStore:
    paths: LocalArtifactPaths

    def trace_part(self, part_number: str, *, limit: int = 8) -> JsonDict:
        return _build_local_trace(self.paths, part=part_number, limit=limit)

    def trace_page(self, page_id: str, *, limit: int = 8) -> JsonDict:
        return _build_local_trace(self.paths, page=page_id, limit=limit)

    def trace_vector_payload(self, *, page_id: str, chunk_id: Optional[str] = None, score: float = 0.0, limit: int = 8) -> JsonDict:
        return _build_local_trace(self.paths, vector_page=page_id, vector_chunk=chunk_id, vector_score=score, limit=limit)


@dataclass
class LocalSourceStore:
    catalog: LocalCatalogStore

    def get_page_source(self, page_id: str) -> JsonDict:
        page = self.catalog.get_page(page_id)
        if page.get("status") != "ok":
            return page
        return {"status": "ok", "page_id": page_id, "source": page.get("source", {})}


@dataclass
class LocalFeedbackStore:
    paths: LocalArtifactPaths

    def save_feedback(self, feedback: Mapping[str, Any]) -> JsonDict:
        self.paths.feedback_jsonl.parent.mkdir(parents=True, exist_ok=True)
        record = dict(feedback)
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        record.setdefault("feedback_id", _feedback_id(record))
        with self.paths.feedback_jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        summary = self.summary()
        _write_json(self.paths.feedback_summary, summary)
        return {"status": "ok", "feedback_id": record["feedback_id"], "summary": summary}

    def summary(self) -> JsonDict:
        rows = _read_jsonl(self.paths.feedback_jsonl)
        by_rating: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        for row in rows:
            by_rating[str(row.get("rating", "unknown"))] = by_rating.get(str(row.get("rating", "unknown")), 0) + 1
            by_category[str(row.get("category", "unknown"))] = by_category.get(str(row.get("category", "unknown")), 0) + 1
        return {
            "status": "ok",
            "total": len(rows),
            "by_rating": by_rating,
            "by_category": by_category,
            "latest": rows[-5:],
        }


@dataclass
class LocalQualityStore:
    paths: LocalArtifactPaths

    def status(self) -> JsonDict:
        quality = _load_json(self.paths.quality_gate_file, default={})
        manifest = _load_json(self.paths.manifest_file, default={})
        graph_quality = _load_json(self.paths.graph_dir / "graph_quality.json", default={})
        return {
            "status": "ok" if (quality or manifest or graph_quality) else "missing",
            "quality_gate": quality,
            "manifest": manifest,
            "graph_quality": graph_quality,
        }


# ---------------------------------------------------------------------------
# Future production placeholders.  These fail clearly until wired.
# ---------------------------------------------------------------------------

class NotConfiguredStoreError(NotImplementedError):
    pass


@dataclass
class PostgresCatalogStore:
    dsn: str

    def _not_configured(self) -> None:
        raise NotConfiguredStoreError("PostgresCatalogStore is a skeleton; wire psycopg/SQL queries before use.")

    def organization_summary(self) -> JsonDict: self._not_configured()
    def get_part(self, part_number: str, *, limit: int = 10) -> JsonDict: self._not_configured()
    def get_page(self, page_id: str) -> JsonDict: self._not_configured()
    def get_ata(self, ata_code: str, *, limit: int = 20) -> JsonDict: self._not_configured()


@dataclass
class OpenSearchKeywordSearchStore:
    url: str
    index: str

    def search(self, query: str, *, limit: int = 10) -> JsonDict:
        raise NotConfiguredStoreError("OpenSearchKeywordSearchStore is a skeleton; wire OpenSearch client before use.")


@dataclass
class QdrantVectorStore:
    url: str
    collection: str

    def trace_payload(self, *, page_id: str, chunk_id: Optional[str] = None, score: float = 0.0) -> JsonDict:
        raise NotConfiguredStoreError("QdrantVectorStore is a skeleton; wire qdrant-client before use.")


@dataclass
class ResCartaSourceStore:
    base_url: str

    def get_page_source(self, page_id: str) -> JsonDict:
        raise NotConfiguredStoreError("ResCartaSourceStore is a skeleton; wire real ResCarta links before use.")


def _build_local_trace(paths: LocalArtifactPaths, **kwargs: Any) -> JsonDict:
    try:
        from tiff.document_graph_traceability import build_traceability_report
    except Exception as exc:  # pragma: no cover - optional module during minimal tests
        return {"status": "error", "error": f"traceability module unavailable: {exc}"}

    try:
        report = build_traceability_report(graph_dir=paths.graph_dir, strict=True, **kwargs)
    except TypeError:
        # Some older helper versions may not accept strict.
        report = build_traceability_report(graph_dir=paths.graph_dir, **kwargs)
    if hasattr(report, "to_jsonable"):
        return report.to_jsonable()
    if isinstance(report, dict):
        return report
    return {"status": "ok", "report": report}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _load_json(path: Path, *, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _read_jsonl(path: Path) -> List[JsonDict]:
    if not path.exists():
        return []
    rows: List[JsonDict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _iter_collection(data: Any, *keys: str) -> Iterable[JsonDict]:
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
                return
        # Common shape: {"120-...": {...}}
        for value in data.values():
            if isinstance(value, dict):
                yield value


def _walk_json_dicts(data: Any) -> Iterable[JsonDict]:
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _walk_json_dicts(value)
    elif isinstance(data, list):
        for item in data:
            yield from _walk_json_dicts(item)


def _extract_list(data: Mapping[str, Any], *keys: str) -> List[Any]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _value_from_ref(ref: Any, *keys: str) -> Optional[Any]:
    if isinstance(ref, str):
        return _strip_graph_prefix(ref, "page")
    if isinstance(ref, dict):
        for key in keys:
            if ref.get(key):
                return _strip_graph_prefix(str(ref[key]), "page")
    return None


def _first_nonempty(data: Mapping[str, Any], *keys: str) -> Optional[Any]:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _normalize_part(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("part:", "")
    value = value.replace("_", "-")
    value = "".join(ch for ch in value if ch.isalnum() or ch == "-")
    return value


def _norm_text(value: str) -> str:
    return " ".join(value.lower().replace("_", "-").split())


def _strip_graph_prefix(value: str, prefix: str) -> str:
    if value.startswith(prefix + ":"):
        return value.split(":", 1)[1]
    return value


def _node_type(node: Mapping[str, Any]) -> Optional[str]:
    return node.get("type") or node.get("node_type") or node.get("kind")


def _feedback_id(record: Mapping[str, Any]) -> str:
    base = "|".join(str(record.get(k, "")) for k in ("question", "rating", "category", "reason", "created_at"))
    return "fb_" + str(abs(hash(base)))


# ---------------------------------------------------------------------------
# Backward-compatible adapter names used by earlier scripts/tests.
# ---------------------------------------------------------------------------

class LocalArtifactCatalogStore:
    """Compatibility wrapper around LocalCatalogStore.

    Earlier scripts expected this class to return plain records or None.  The
    refactored API uses LocalCatalogStore, which returns status-wrapped records.
    Keep both contracts so old checks and the new service layer can coexist.
    """

    def __init__(self, paths: LocalArtifactPaths):
        self.paths = paths.resolve() if hasattr(paths, "resolve") else paths
        self._store = LocalCatalogStore(self.paths)

    def organization_summary(self) -> JsonDict:
        result = self._store.organization_summary()
        summary = result.get("summary") if isinstance(result, dict) else None
        if isinstance(summary, dict):
            return {"status": "ok", **summary}
        return result if isinstance(result, dict) else {"status": "missing"}

    def get_part(self, part_number: str) -> JsonDict | None:
        result = self._store.get_part(part_number)
        if not isinstance(result, dict) or result.get("status") != "ok":
            # Compatibility fallback: older callers sometimes pass a compact
            # part number without punctuation, e.g. 12037313001.
            wanted = _compat_part_key(part_number)
            for candidate in _iter_collection(self._store._load_part_tree(), "parts", "items", "part_tree"):
                candidate_number = candidate.get("part_number") or candidate.get("part") or candidate.get("id") or candidate.get("label")
                if candidate_number and _compat_part_key(str(candidate_number)) == wanted:
                    raw = dict(candidate)
                    raw.setdefault("status", "ok")
                    return raw
            return None
        raw = dict(result.get("raw") or {})
        raw.setdefault("part_number", result.get("part_number") or part_number)
        raw.setdefault("nomenclature", result.get("nomenclature"))
        if "pages" not in raw:
            pages = []
            for item in result.get("pages") or []:
                if isinstance(item, dict):
                    pages.append(item.get("page") or {"page_id": item.get("page_id")})
            raw["pages"] = pages
        raw.setdefault("status", "ok")
        return raw

    def get_page(self, page_id: str) -> JsonDict | None:
        result = self._store.get_page(page_id)
        if not isinstance(result, dict) or result.get("status") != "ok":
            return None
        page = dict(result.get("page") or {})
        page.setdefault("page_id", result.get("page_id") or page_id)
        source = result.get("source") or {}
        if isinstance(source, dict):
            for key, value in source.items():
                page.setdefault(key, value)
        context = result.get("context")
        if context:
            page.setdefault("context", context)
        page.setdefault("status", "ok")
        return page

    def get_ata(self, ata_code: str) -> JsonDict | None:
        result = self._store.get_ata(ata_code)
        if not isinstance(result, dict) or result.get("status") != "ok":
            return None
        raw = dict(result.get("raw") or {})
        raw.setdefault("ata_code", result.get("ata_code") or ata_code)
        raw.setdefault("manual", result.get("manual"))
        raw.setdefault("pages", result.get("pages") or [])
        raw.setdefault("status", "ok")
        return raw


class LocalJsonlFeedbackStore:
    """Compatibility wrapper around LocalFeedbackStore."""

    def __init__(self, paths: LocalArtifactPaths):
        self.paths = paths.resolve() if hasattr(paths, "resolve") else paths
        self._store = LocalFeedbackStore(self.paths)

    def submit_feedback(self, feedback: Mapping[str, Any]) -> JsonDict:
        return self._store.save_feedback(feedback)

    def feedback_summary(self) -> JsonDict:
        return self._store.summary()


# Old name used by previous production-placeholder tests.
OpenSearchKeywordStore = OpenSearchKeywordSearchStore


# Keep QdrantVectorStore compatible with both old and new expectations.
# The old test expected .search() to raise NotImplementedError; the new design
# expects .trace_payload() to exist as the future Qdrant handoff boundary.
def _qdrant_search_not_configured(self, query: str, *, limit: int = 10, filters: Mapping[str, Any] | None = None) -> list[JsonDict]:
    raise NotConfiguredStoreError("QdrantVectorStore is a skeleton; wire qdrant-client before use.")

try:
    QdrantVectorStore.search = _qdrant_search_not_configured  # type: ignore[attr-defined]
except NameError:  # pragma: no cover
    pass


def build_local_store_bundle(repo_root: str | Path | None = None, config_path: str | Path = "local_config.yaml") -> StoreBundle:
    """Compatibility factory for the local store bundle.

    ``config_path`` is accepted for API compatibility; the local artifact stores
    do not need it directly.
    """

    root = Path(repo_root) if repo_root is not None else Path(".")
    return create_local_store_bundle(root)


def adapter_readiness(
    bundle: StoreBundle,
    *,
    part_probe: str = "120-37313-001",
    page_probe: str = "t_p_120_1176_p000083",
) -> JsonDict:
    """Return a small machine-readable adapter readiness report."""

    org_summary = _safe_call(lambda: bundle.catalog.organization_summary(), default={})
    part_result = _safe_call(lambda: bundle.catalog.get_part(part_probe), default=None)
    page_result = _safe_call(lambda: bundle.catalog.get_page(page_probe), default=None)
    quality_result = _safe_call(lambda: bundle.quality.status(), default={})

    part_found = _is_found(part_result)
    page_found = _is_found(page_result)
    part_pages = _part_pages_count(part_result)
    page_has_source = _page_has_source(page_result)
    quality_status = _extract_quality_status(quality_result)

    status = "ok" if org_summary and part_found and page_found and page_has_source else "needs_attention"
    return {
        "status": status,
        "mode": getattr(bundle, "mode", "local_artifacts"),
        "organization_summary_present": bool(org_summary),
        "part_probe": {
            "part_number": part_probe,
            "found": part_found,
            "nomenclature": _extract_nomenclature(part_result),
            "pages": part_pages,
        },
        "page_probe": {
            "page_id": page_probe,
            "found": page_found,
            "has_source": page_has_source,
        },
        "quality_status": quality_status,
    }


def _safe_call(fn, *, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _is_found(value: Any) -> bool:
    if not isinstance(value, dict):
        return value is not None
    status = str(value.get("status", "")).lower()
    if status in {"ok", "found"}:
        return True
    if status in {"not_found", "missing", "failed", "error"}:
        return False
    return bool(value)


def _part_pages_count(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    for key in ("pages_count", "page_count", "pages_total", "mentions"):
        try:
            if value.get(key) is not None:
                return int(value[key])
        except Exception:
            pass
    pages = value.get("pages")
    if isinstance(pages, list):
        return len(pages)
    return None


def _extract_nomenclature(value: Any) -> Any:
    if not isinstance(value, dict):
        return None
    return value.get("nomenclature") or value.get("name") or value.get("label")


def _page_has_source(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    source = value.get("source")
    if isinstance(source, dict) and any(source.get(k) for k in ("source_url", "rescarta_url", "tiff_path", "ocr_path")):
        return True
    return any(value.get(k) for k in ("source_url", "rescarta_url", "tiff_path", "source_image_path", "ocr_path", "ocr_text_path"))


def _extract_quality_status(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("status", "pipeline_status"):
        if value.get(key):
            return str(value[key]).lower()
    for nested_key in ("quality_gate", "manifest", "graph_quality"):
        nested = value.get(nested_key)
        if isinstance(nested, dict) and nested.get("status"):
            return str(nested["status"]).lower()
    return None


def _compat_part_key(value: str) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())
