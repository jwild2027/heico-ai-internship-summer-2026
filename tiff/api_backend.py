"""API backend boundary helpers for the TIFF/RAG local MVP.

This module is intentionally storage-light.  It reads the current local
artifacts (JSON graph/export files and command-line RAG entrypoints) through a
small stable interface that can later be backed by PostgreSQL, OpenSearch, and
Qdrant without changing the API/UI contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import time
from typing import Any
import uuid

try:  # The graph modules are added by the graph/traceability patches.
    from tiff.document_graph_traversal import GraphStore, context_score
    from tiff.document_graph_traceability import build_traceability_report
except Exception:  # pragma: no cover - keeps this module importable in minimal tests.
    GraphStore = None  # type: ignore[assignment]
    context_score = None  # type: ignore[assignment]
    build_traceability_report = None  # type: ignore[assignment]



if GraphStore is None:
    from dataclasses import dataclass as _dataclass
    from collections import defaultdict as _defaultdict
    import re as _re

    @_dataclass(frozen=True)
    class _FallbackNode:
        id: str
        type: str
        label: str
        raw: dict[str, Any]

        def prop(self, *names: str, default: Any = None) -> Any:
            for name in names:
                if self.raw.get(name) not in (None, ""):
                    return self.raw[name]
                props = self.raw.get("properties")
                if isinstance(props, dict) and props.get(name) not in (None, ""):
                    return props[name]
                data = self.raw.get("data")
                if isinstance(data, dict) and data.get(name) not in (None, ""):
                    return data[name]
            return default

    @_dataclass(frozen=True)
    class _FallbackEdge:
        type: str
        source: str
        target: str
        raw: dict[str, Any]

    class _FallbackGraphStore:
        def __init__(self, nodes: list[_FallbackNode], edges: list[_FallbackEdge], graph_dir: Path):
            self.nodes = nodes
            self.edges = edges
            self.graph_dir = graph_dir
            self.nodes_by_id = {node.id: node for node in nodes}
            self.nodes_by_type: dict[str, list[_FallbackNode]] = _defaultdict(list)
            self.out_edges: dict[str, list[_FallbackEdge]] = _defaultdict(list)
            self.in_edges: dict[str, list[_FallbackEdge]] = _defaultdict(list)
            for node in nodes:
                self.nodes_by_type[node.type].append(node)
            for edge in edges:
                self.out_edges[edge.source].append(edge)
                self.in_edges[edge.target].append(edge)

        @classmethod
        def load(cls, graph_dir: str | Path):
            graph_dir = Path(graph_dir)
            nodes_raw = _json_list(graph_dir / "graph_nodes.json")
            edges_raw = _json_list(graph_dir / "graph_edges.json")
            nodes = []
            for row in nodes_raw:
                node_id = str(_first_value(row, ("id", "node_id"), ""))
                node_type = str(_first_value(row, ("type", "node_type", "kind"), "unknown"))
                label = str(_first_value(row, ("label", "name", "title"), node_id))
                nodes.append(_FallbackNode(node_id, node_type, label, row))
            edges = []
            for row in edges_raw:
                source = str(_first_value(row, ("source", "from", "from_id"), ""))
                target = str(_first_value(row, ("target", "to", "to_id"), ""))
                etype = str(_first_value(row, ("type", "edge_type", "relationship"), "UNKNOWN"))
                edges.append(_FallbackEdge(etype, source, target, row))
            return cls(nodes, edges, graph_dir)

        def neighbors(self, node_id: str, edge_type: str | None = None, direction: str = "out"):
            edges = self.out_edges.get(node_id, []) if direction == "out" else self.in_edges.get(node_id, [])
            result = []
            for edge in edges:
                if edge_type is not None and edge.type != edge_type:
                    continue
                other_id = edge.target if direction == "out" else edge.source
                other = self.nodes_by_id.get(other_id)
                if other is not None:
                    result.append((edge, other))
            return result

        def find_one(self, node_type: str, query: str | None = None):
            nodes = self.nodes_by_type.get(node_type, [])
            if not nodes:
                return None
            if query is None:
                return nodes[0]
            q = _norm_value(query)
            for node in nodes:
                fields = [node.id, node.label, node.prop("part_number", default=""), node.prop("page_id", default=""), node.prop("ata_code", default="")]
                if any(q == _norm_value(field) or q in _norm_value(field) for field in fields if field):
                    return node
            return None

        def find_part(self, part_number: str | None = None):
            return self.find_one("part", part_number) if part_number else self.find_one("part")

        def find_page(self, page_id: str | None = None):
            return self.find_one("page", page_id) if page_id else self.find_one("page")

    def _json_list(path: Path) -> list[dict[str, Any]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            for key in ("nodes", "edges", "items", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
        return []

    def _first_value(row: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
        for key in keys:
            if row.get(key) not in (None, ""):
                return row[key]
            for container in ("properties", "data"):
                nested = row.get(container)
                if isinstance(nested, dict) and nested.get(key) not in (None, ""):
                    return nested[key]
        return default

    def _norm_value(value: Any) -> str:
        return _re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")

    def _fallback_context_score(node: Any | None) -> float:
        if node is None:
            return 0.0
        confidence = str(node.prop("confidence", default="")).lower()
        return {"high": 0.9, "medium": 0.65, "low": 0.35}.get(confidence, 0.5)

    GraphStore = _FallbackGraphStore  # type: ignore[assignment]
    context_score = _fallback_context_score  # type: ignore[assignment]

DEFAULT_GRAPH_DIR = Path("local_data/organization/graph")
DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_FEEDBACK_JSONL = Path("local_data/feedback/api_feedback.jsonl")
DEFAULT_FEEDBACK_SUMMARY = Path("local_data/feedback/api_feedback_summary.json")
DEFAULT_QUALITY_JSON = Path("local_data/pipeline_runs/latest_quality_gate.json")
DEFAULT_MANIFEST_JSON = Path("local_data/pipeline_runs/latest_backend_pipeline.json")
DEFAULT_GRAPH_QUALITY_JSON = Path("local_data/organization/graph/graph_quality.json")
DEFAULT_USER_QUERY_JSON = Path("local_data/evals/user_query/user_query_test_results.json")
DEFAULT_REALISTIC_QUERY_JSON = Path("local_data/evals/realistic_query_trace/realistic_query_trace_results.json")


@dataclass(frozen=True)
class ApiPaths:
    graph_dir: Path = DEFAULT_GRAPH_DIR
    export_dir: Path = DEFAULT_EXPORT_DIR
    feedback_jsonl: Path = DEFAULT_FEEDBACK_JSONL
    feedback_summary: Path = DEFAULT_FEEDBACK_SUMMARY
    quality_json: Path = DEFAULT_QUALITY_JSON
    manifest_json: Path = DEFAULT_MANIFEST_JSON
    graph_quality_json: Path = DEFAULT_GRAPH_QUALITY_JSON
    user_query_json: Path = DEFAULT_USER_QUERY_JSON
    realistic_query_json: Path = DEFAULT_REALISTIC_QUERY_JSON


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
class FeedbackRecord:
    feedback_id: str
    question: str
    rating: str
    category: str
    reason: str
    answer_id: str | None = None
    answer_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "created_at": self.created_at,
            "question": self.question,
            "rating": self.rating,
            "category": self.category,
            "reason": self.reason,
            "answer_id": self.answer_id,
            "answer_text": self.answer_text,
            "metadata": self.metadata,
        }


def api_status(paths: ApiPaths | None = None) -> dict[str, Any]:
    """Return a compact readiness/status object for API/UI clients."""
    paths = paths or ApiPaths()
    quality = _load_json(paths.quality_json, default={})
    manifest = _load_json(paths.manifest_json, default={})
    graph_quality = _load_json(paths.graph_quality_json, default={})
    user_query = _load_json(paths.user_query_json, default={})
    realistic_query = _load_json(paths.realistic_query_json, default={})

    q_summary = _dict_get(quality, "summary", default={})
    g_summary = _dict_get(graph_quality, "summary", default=graph_quality if isinstance(graph_quality, dict) else {})

    return {
        "status": _dict_get(quality, "status", default=_dict_get(manifest, "status", default="unknown")),
        "pipeline_status": _dict_get(q_summary, "pipeline_status", default=_dict_get(manifest, "pipeline_status", "unknown")),
        "graph_quality_status": _dict_get(graph_quality, "status", default="unknown"),
        "graph": {
            "present": bool(_dict_get(g_summary, "graph_present", default=False)),
            "nodes_total": _dict_get(g_summary, "nodes_total"),
            "edges_total": _dict_get(g_summary, "edges_total"),
            "page_nodes": _dict_get(g_summary, "page_nodes"),
            "page_context_nodes": _dict_get(g_summary, "page_context_nodes"),
            "source_link_nodes": _dict_get(g_summary, "source_link_nodes"),
            "pages_without_context": _dict_get(g_summary, "pages_without_context"),
            "pages_without_source_links": _dict_get(g_summary, "pages_without_source_links"),
        },
        "query_tests": {
            "user_query_present": bool(_dict_get(g_summary, "user_query_results_present", default=False)) or bool(user_query),
            "user_query_total": _dict_get(g_summary, "user_query_total", default=_dict_get(user_query, "total")),
            "user_query_fail": _dict_get(g_summary, "user_query_fail", default=_dict_get(user_query, "fail")),
            "realistic_present": bool(_dict_get(g_summary, "realistic_query_results_present", default=False)) or bool(realistic_query),
            "realistic_total": _dict_get(g_summary, "realistic_query_total"),
            "realistic_fail": _dict_get(g_summary, "realistic_query_fail"),
        },
        "artifact_paths": {
            "graph_dir": str(paths.graph_dir),
            "export_dir": str(paths.export_dir),
            "quality_json": str(paths.quality_json),
            "graph_quality_json": str(paths.graph_quality_json),
        },
    }


def organization_summary(paths: ApiPaths | None = None) -> dict[str, Any]:
    paths = paths or ApiPaths()
    summary = _load_json(paths.export_dir / "organization_summary.json", default={})
    graph_quality = _load_json(paths.graph_quality_json, default={})
    return {"organization_summary": summary, "graph_quality": graph_quality}


def part_lookup(part_number: str, paths: ApiPaths | None = None, limit: int = 8) -> dict[str, Any]:
    graph = _load_graph(paths)
    part = graph.find_part(part_number)
    if part is None:
        return {"status": "not_found", "part_number": part_number, "pages": []}
    nomenclature_nodes = _neighbors(graph, part.id, "HAS_NOMENCLATURE", "nomenclature")
    pages = _part_pages(graph, part)[:limit]
    return {
        "status": "ok",
        "part_number": part.prop("part_number", default=part.label),
        "part_node": _node_obj(part),
        "nomenclature": nomenclature_nodes[0].label if nomenclature_nodes else None,
        "pages_total": len(_part_pages(graph, part)),
        "pages": [_page_obj(graph, page) for page in pages],
    }


def page_lookup(page_id: str, paths: ApiPaths | None = None, limit: int = 8) -> dict[str, Any]:
    graph = _load_graph(paths)
    page = graph.find_page(page_id)
    if page is None:
        return {"status": "not_found", "page_id": page_id}
    parts = _neighbors(graph, page.id, "MENTIONS_PART", "part")[:limit]
    return {"status": "ok", "page": _page_obj(graph, page), "parts": [_part_obj(graph, part) for part in parts]}


def ata_lookup(ata_code: str, paths: ApiPaths | None = None, limit: int = 12) -> dict[str, Any]:
    graph = _load_graph(paths)
    ata = graph.find_one("ata_section", ata_code)
    if ata is None:
        return {"status": "not_found", "ata_code": ata_code, "pages": []}
    pages = _neighbors(graph, ata.id, "CONTAINS_PAGE", "page")
    return {
        "status": "ok",
        "ata": _node_obj(ata),
        "pages_total": len(pages),
        "pages": [_page_obj(graph, page) for page in pages[:limit]],
    }


def trace_part(part_number: str, paths: ApiPaths | None = None, limit: int = 8) -> dict[str, Any]:
    if build_traceability_report is None:
        raise RuntimeError("document graph traceability module is not available")
    paths = paths or ApiPaths()
    report = build_traceability_report(graph_dir=paths.graph_dir, part=part_number, limit=limit, strict=True)
    return report.to_jsonable()


def trace_page(page_id: str, paths: ApiPaths | None = None, limit: int = 8) -> dict[str, Any]:
    if build_traceability_report is None:
        raise RuntimeError("document graph traceability module is not available")
    paths = paths or ApiPaths()
    report = build_traceability_report(graph_dir=paths.graph_dir, page=page_id, limit=limit, strict=True)
    return report.to_jsonable()


def trace_vector_payload(page_id: str, chunk_id: str | None = None, score: float | None = None, paths: ApiPaths | None = None, limit: int = 8) -> dict[str, Any]:
    if build_traceability_report is None:
        raise RuntimeError("document graph traceability module is not available")
    paths = paths or ApiPaths()
    report = build_traceability_report(
        graph_dir=paths.graph_dir,
        vector_page=page_id,
        vector_chunk=chunk_id,
        vector_score=score,
        limit=limit,
        strict=True,
    )
    return report.to_jsonable()


def ask_question(question: str, config: str = "local_config.yaml", repo_root: str | Path = ".", timeout_seconds: int = 240) -> AskResult:
    command = [sys.executable, "scripts/ask_tiff_rag.py", "--config", config, question]
    start = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=repo_root,
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
    question: str,
    rating: str,
    category: str,
    reason: str,
    answer_text: str | None = None,
    answer_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    paths: ApiPaths | None = None,
) -> dict[str, Any]:
    paths = paths or ApiPaths()
    record = FeedbackRecord(
        feedback_id=f"fb_{uuid.uuid4().hex}",
        question=question,
        rating=rating,
        category=category,
        reason=reason,
        answer_text=answer_text,
        answer_id=answer_id,
        metadata=metadata or {},
    )
    paths.feedback_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with paths.feedback_jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.to_jsonable(), ensure_ascii=False) + "\n")
    summary = summarize_feedback(paths)
    paths.feedback_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {"status": "ok", "feedback": record.to_jsonable(), "summary": summary}


def summarize_feedback(paths: ApiPaths | None = None) -> dict[str, Any]:
    paths = paths or ApiPaths()
    rows = []
    if paths.feedback_jsonl.exists():
        for line in paths.feedback_jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    rating_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for row in rows:
        rating = str(row.get("rating") or "unknown")
        category = str(row.get("category") or "unknown")
        rating_counts[rating] = rating_counts.get(rating, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
    return {
        "total_feedback": len(rows),
        "rating_counts": dict(sorted(rating_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "feedback_jsonl": str(paths.feedback_jsonl),
    }


def _load_graph(paths: ApiPaths | None = None):
    if GraphStore is None:
        raise RuntimeError("document graph traversal module is not available")
    paths = paths or ApiPaths()
    return GraphStore.load(paths.graph_dir)


def _node_obj(node: Any | None) -> dict[str, Any] | None:
    if node is None:
        return None
    return {"id": node.id, "type": node.type, "label": node.label, "properties": dict(node.raw.get("properties") or {})}


def _part_obj(graph: Any, part: Any) -> dict[str, Any]:
    names = _neighbors(graph, part.id, "HAS_NOMENCLATURE", "nomenclature")
    return {
        "part_number": part.prop("part_number", default=part.label),
        "node": _node_obj(part),
        "nomenclature": names[0].label if names else None,
    }


def _page_obj(graph: Any, page: Any) -> dict[str, Any]:
    doc = _first_neighbor(graph, page.id, "BELONGS_TO_DOCUMENT", "document")
    ata = _first_neighbor(graph, page.id, "BELONGS_TO_ATA", "ata_section")
    source = _first_neighbor(graph, page.id, "HAS_SOURCE_LINK", "source_link")
    context = _first_neighbor(graph, page.id, "HAS_CONTEXT", "page_context")
    score = context_score(context) if context is not None and context_score is not None else 0.0
    return {
        "page_id": page.prop("page_id", default=page.label),
        "node": _node_obj(page),
        "label": page.prop("page_label", "label", default=page.label),
        "document": doc.label if doc else None,
        "ata": ata.label if ata else None,
        "source_link_present": source is not None,
        "source_link": _node_obj(source),
        "context_present": context is not None,
        "context_score": score,
        "context_summary": _context_summary(context),
    }


def _context_summary(node: Any | None) -> str | None:
    if node is None:
        return None
    for key in ("short_summary", "summary", "context", "text"):
        value = node.prop(key, default=None)
        if value:
            return str(value)
    return node.label


def _neighbors(graph: Any, node_id: str, edge_type: str, node_type: str | None = None) -> list[Any]:
    result = []
    for _edge, node in graph.neighbors(node_id, edge_type=edge_type, direction="out"):
        if node_type is None or node.type == node_type:
            result.append(node)
    return result


def _first_neighbor(graph: Any, node_id: str, edge_type: str, node_type: str | None = None) -> Any | None:
    nodes = _neighbors(graph, node_id, edge_type, node_type)
    return nodes[0] if nodes else None


def _part_pages(graph: Any, part: Any) -> list[Any]:
    seen = set()
    pages = []
    for edge_name in ("APPEARS_ON",):
        for _edge, page in graph.neighbors(part.id, edge_type=edge_name, direction="out"):
            if page.type == "page" and page.id not in seen:
                seen.add(page.id)
                pages.append(page)
    # Fallback: part -> HAS_MENTION -> PartMention -> FOUND_ON -> Page.
    for _edge, mention in graph.neighbors(part.id, edge_type="HAS_MENTION", direction="out"):
        for _edge2, page in graph.neighbors(mention.id, edge_type="FOUND_ON", direction="out"):
            if page.type == "page" and page.id not in seen:
                seen.add(page.id)
                pages.append(page)
    return sorted(pages, key=lambda n: n.id)


def _load_json(path: Path, default: Any = None) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _dict_get(data: Any, key: str, default: Any = None) -> Any:
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def _preview(text: str, limit: int = 1200) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."
