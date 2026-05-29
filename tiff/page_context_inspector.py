"""Inspect generated AI page-context graph artifacts.

This module is intentionally read-only. It validates the JSON written by
scripts/generate_page_contexts.py and helps decide whether a larger page-context
scan is ready to run.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any, Iterable


DEFAULT_CONTEXT_FILE = Path("local_data/organization/context/page_contexts.json")
DEFAULT_GRAPH_SUMMARY = Path("local_data/organization/graph/graph_summary.json")


@dataclass(frozen=True)
class ContextRow:
    page_id: str
    page_label: str = ""
    manual: str = ""
    ata: str = ""
    page_role: str = "unknown"
    confidence: str = "unknown"
    summary: str = ""
    topics: tuple[str, ...] = ()
    important_parts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass
class ContextInspection:
    status: str
    context_file: str
    graph_summary_file: str | None
    total_contexts: int = 0
    contexts_with_warnings: int = 0
    contexts_with_errors: int = 0
    role_counts: dict[str, int] = field(default_factory=dict)
    confidence_counts: dict[str, int] = field(default_factory=dict)
    warning_counts: dict[str, int] = field(default_factory=dict)
    topic_counts: dict[str, int] = field(default_factory=dict)
    highlighted_part_count: int = 0
    unique_highlighted_parts: int = 0
    graph_page_context_nodes: int | None = None
    graph_has_context_edges: int | None = None
    graph_tagged_as_edges: int | None = None
    graph_highlights_part_edges: int | None = None
    selected_contexts: list[dict[str, Any]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "context_file": self.context_file,
            "graph_summary_file": self.graph_summary_file,
            "total_contexts": self.total_contexts,
            "contexts_with_warnings": self.contexts_with_warnings,
            "contexts_with_errors": self.contexts_with_errors,
            "role_counts": self.role_counts,
            "confidence_counts": self.confidence_counts,
            "warning_counts": self.warning_counts,
            "topic_counts": self.topic_counts,
            "highlighted_part_count": self.highlighted_part_count,
            "unique_highlighted_parts": self.unique_highlighted_parts,
            "graph_page_context_nodes": self.graph_page_context_nodes,
            "graph_has_context_edges": self.graph_has_context_edges,
            "graph_tagged_as_edges": self.graph_tagged_as_edges,
            "graph_highlights_part_edges": self.graph_highlights_part_edges,
            "selected_contexts": self.selected_contexts,
            "issues": self.issues,
        }


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, tuple):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(value)]


def _first_nonempty(row: dict[str, Any], names: Iterable[str], default: str = "") -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value)
    return default


def parse_context_row(row: dict[str, Any]) -> ContextRow:
    page_id = _first_nonempty(row, ["page_id", "id", "source_page_id"], "")
    page_role = _first_nonempty(row, ["page_role", "role", "document_role"], "unknown")
    confidence = _first_nonempty(row, ["confidence", "confidence_level"], "unknown")
    summary = _first_nonempty(row, ["short_summary", "summary", "long_summary", "context"], "")
    manual = _first_nonempty(row, ["manual", "manual_title", "publication_number", "document_title"], "")
    ata = _first_nonempty(row, ["ata", "ata_code"], "")
    page_label = _first_nonempty(row, ["page_label", "label"], "")
    topics = tuple(_as_list(row.get("topics") or row.get("detected_topics") or row.get("topic_tags")))
    important_parts = tuple(_as_list(row.get("important_parts") or row.get("highlighted_parts") or row.get("parts")))
    warnings = tuple(_as_list(row.get("warnings") or row.get("warning") or row.get("warning_categories")))
    errors = tuple(_as_list(row.get("errors") or row.get("error") or row.get("error_categories")))
    return ContextRow(
        page_id=page_id,
        page_label=page_label,
        manual=manual,
        ata=ata,
        page_role=page_role,
        confidence=confidence,
        summary=summary,
        topics=topics,
        important_parts=important_parts,
        warnings=warnings,
        errors=errors,
    )


def load_context_rows(path: Path = DEFAULT_CONTEXT_FILE) -> list[ContextRow]:
    data = _load_json(path)
    if isinstance(data, dict):
        rows = data.get("contexts") or data.get("page_contexts") or data.get("items") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    return [parse_context_row(row) for row in rows if isinstance(row, dict)]


def _load_graph_counts(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = _load_json(path)
    if not isinstance(data, dict):
        return {}
    return data


def _nested_count(data: dict[str, Any], bucket_names: list[str], key: str) -> int | None:
    """Read a count from old and new graph summary shapes.

    Supported examples:
      {"node_types": {"page_context": 10}}
      {"graph_counts": {"node_types": {"page_context": 10}}}
      {"nodes_by_type": {"page_context": 10}}
    """
    candidates: list[dict[str, Any]] = []
    candidates.append(data)
    graph_counts = data.get("graph_counts") if isinstance(data, dict) else None
    if isinstance(graph_counts, dict):
        candidates.append(graph_counts)

    for parent in candidates:
        for bucket_name in bucket_names:
            bucket = parent.get(bucket_name)
            if isinstance(bucket, dict) and key in bucket:
                try:
                    return int(bucket[key])
                except Exception:
                    return None
    return None


def inspect_page_contexts(
    context_file: Path = DEFAULT_CONTEXT_FILE,
    graph_summary_file: Path | None = DEFAULT_GRAPH_SUMMARY,
    page_ids: Iterable[str] = (),
    roles: Iterable[str] = (),
    topics: Iterable[str] = (),
    limit: int = 10,
    strict: bool = False,
) -> ContextInspection:
    issues: list[str] = []
    context_file = Path(context_file)
    if not context_file.exists():
        status = "FAIL" if strict else "NEEDS_ATTENTION"
        return ContextInspection(
            status=status,
            context_file=str(context_file),
            graph_summary_file=str(graph_summary_file) if graph_summary_file else None,
            issues=[f"context file not found: {context_file}"],
        )

    rows = load_context_rows(context_file)
    if not rows:
        issues.append("no page contexts were found")

    role_counts = Counter(row.page_role or "unknown" for row in rows)
    confidence_counts = Counter(row.confidence or "unknown" for row in rows)
    warning_counts = Counter(w for row in rows for w in row.warnings)
    topic_counts = Counter(t for row in rows for t in row.topics)
    highlighted_parts = [p for row in rows for p in row.important_parts]

    page_filter = {p.strip() for p in page_ids if p.strip()}
    role_filter = {r.strip().lower() for r in roles if r.strip()}
    topic_filter = {t.strip().lower() for t in topics if t.strip()}

    selected = []
    for row in rows:
        if page_filter and row.page_id not in page_filter:
            continue
        if role_filter and row.page_role.lower() not in role_filter:
            continue
        if topic_filter and not any(t.lower() in topic_filter for t in row.topics):
            continue
        selected.append(row)

    if (page_filter or role_filter or topic_filter) and not selected:
        issues.append("filters matched no contexts")

    graph_counts = {}
    if graph_summary_file:
        graph_summary_file = Path(graph_summary_file)
        graph_counts = _load_graph_counts(graph_summary_file)

    graph_page_context_nodes = _nested_count(graph_counts, ["node_types", "nodes_by_type"], "page_context")
    graph_has_context_edges = _nested_count(graph_counts, ["edge_types", "edges_by_type"], "HAS_CONTEXT")
    graph_tagged_as_edges = _nested_count(graph_counts, ["edge_types", "edges_by_type"], "TAGGED_AS")
    graph_highlights_part_edges = _nested_count(graph_counts, ["edge_types", "edges_by_type"], "HIGHLIGHTS_PART")

    if strict:
        if not rows:
            issues.append("strict mode requires at least one context")
        if graph_summary_file and graph_summary_file.exists():
            if graph_page_context_nodes is not None and graph_page_context_nodes < len(rows):
                issues.append("graph page_context node count is lower than context count")
            if graph_has_context_edges is not None and graph_has_context_edges < len(rows):
                issues.append("graph HAS_CONTEXT edge count is lower than context count")

    status = "OK" if not [i for i in issues if "warning" not in i.lower()] else "NEEDS_ATTENTION"
    if strict and issues:
        status = "FAIL"

    selected_contexts = [
        {
            "page_id": row.page_id,
            "page_label": row.page_label,
            "manual": row.manual,
            "ata": row.ata,
            "page_role": row.page_role,
            "confidence": row.confidence,
            "summary": row.summary,
            "topics": list(row.topics),
            "important_parts": list(row.important_parts),
            "warnings": list(row.warnings),
            "errors": list(row.errors),
        }
        for row in selected[:limit]
    ]

    return ContextInspection(
        status=status,
        context_file=str(context_file),
        graph_summary_file=str(graph_summary_file) if graph_summary_file else None,
        total_contexts=len(rows),
        contexts_with_warnings=sum(1 for row in rows if row.warnings),
        contexts_with_errors=sum(1 for row in rows if row.errors),
        role_counts=dict(sorted(role_counts.items())),
        confidence_counts=dict(sorted(confidence_counts.items())),
        warning_counts=dict(sorted(warning_counts.items())),
        topic_counts=dict(topic_counts.most_common(20)),
        highlighted_part_count=len(highlighted_parts),
        unique_highlighted_parts=len(set(highlighted_parts)),
        graph_page_context_nodes=graph_page_context_nodes,
        graph_has_context_edges=graph_has_context_edges,
        graph_tagged_as_edges=graph_tagged_as_edges,
        graph_highlights_part_edges=graph_highlights_part_edges,
        selected_contexts=selected_contexts,
        issues=issues,
    )
