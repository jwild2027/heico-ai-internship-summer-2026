#!/usr/bin/env python3
"""Build a TRACE-Net graph explorer that exposes part nomenclature and PageContextV2.

Drop this file into scripts/ as:

    scripts/build_trace_net_graph_explorer_v2_nomenclature_fix.py

Run from the repo root after the 50-page context v2 job has loaded records:

    export TRACE_NET_DATABASE_URL="postgresql://tracenet:tracenet@localhost:5432/tracenet_dev"
    python scripts/build_trace_net_graph_explorer_v2_nomenclature_fix.py \
      --database-url "$TRACE_NET_DATABASE_URL" \
      --require-first-pages 1-50 \
      --open

This is a read-only UI artifact builder. It reads PostgreSQL, merges the existing
TRACE-Net explorer graph with two missing visual overlays, and writes the same
HTML/JSON files as the existing graph explorer:

    local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer.html
    local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_data.json
    local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_summary.json
    local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_nodes.json
    local_data/organization/trace_net/graph_explorer/trace_net_graph_explorer_edges.json

It does not mutate Postgres/source truth/trust/RAG/feedback data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import webbrowser
from collections import Counter
from pathlib import Path
from typing import Any, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff import trace_net_graph_explorer as base  # noqa: E402

VERSION = "trace_net_graph_explorer_v1_3_context_v2_nomenclature_fix"
PAGE_PART_EDGE_HINTS = {
    "HAS_PART",
    "MENTIONS_PART",
    "PART_ON_PAGE",
    "APPEARS_ON_PAGE",
    "FOUND_ON_PAGE",
    "FOUND_ON",
    "REFERS_TO_PART",
}
CONTEXT_V2_NODE_TYPES = {
    "page_context_v2",
    "pagecontextv2",
    "context_v2",
}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        return "; ".join(_as_text(item) for item in value if _as_text(item))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = _as_text(value)
        if text:
            return text
    return ""


def _field(row: dict[str, Any], *keys: str) -> Any:
    payload = _as_dict(row.get("payload"))
    for key in keys:
        if key in row and row[key] not in (None, "", [], {}):
            return row[key]
        if key in payload and payload[key] not in (None, "", [], {}):
            return payload[key]
    return None


def _safe_suffix(value: Any, *, fallback: str = "node") -> str:
    text = _as_text(value) or fallback
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "_", text).strip("_")
    if not text:
        text = fallback
    if len(text) <= 96:
        return text
    digest = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"{text[:72]}_{digest}"


def _strip_known_prefix(text: str, prefixes: Sequence[str]) -> str:
    cleaned = text.strip()
    lowered = cleaned.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix.lower()):
            return cleaned[len(prefix) :].strip()
    return cleaned


def _page_number_from_any(value: Any) -> Optional[int]:
    text = _as_text(value)
    if not text:
        return None
    num = base._page_num_from_page_id(text)  # type: ignore[attr-defined]
    if num is not None:
        return num
    match = re.search(r"\bpage\s*(\d{1,6})\b", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"\bp(\d{1,6})\b", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _canonical_page_id_any(value: Any, *, fallback_doc: str) -> str:
    text = _as_text(value)
    if not text:
        return ""
    num = _page_number_from_any(text)
    if num is not None:
        return f"{fallback_doc}_p{num:06d}"
    return base.canonical_page_id(text, fallback_doc=fallback_doc)


def _node_lookup(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node.get("id")): node for node in graph.get("nodes", []) if node.get("id")}


def _edge_lookup(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(edge.get("id")): edge for edge in graph.get("edges", []) if edge.get("id")}


def _add_node(graph: dict[str, Any], node: dict[str, Any]) -> bool:
    lookup = _node_lookup(graph)
    node_id = _as_text(node.get("id"))
    if not node_id:
        return False
    existing = lookup.get(node_id)
    if existing is None:
        graph.setdefault("nodes", []).append(node)
        return True
    existing["size"] = max(int(existing.get("size") or 0), int(node.get("size") or 0))
    existing["weight"] = max(float(existing.get("weight") or 0), float(node.get("weight") or 0))
    existing_payload = existing.setdefault("payload", {})
    for key, value in (node.get("payload") or {}).items():
        if existing_payload.get(key) in (None, "", [], {}):
            existing_payload[key] = value
    if not _as_text(existing.get("label")) and _as_text(node.get("label")):
        existing["label"] = node["label"]
    return False


def _add_edge(
    graph: dict[str, Any],
    source: str,
    target: str,
    edge_type: str,
    *,
    weight: float = 1.0,
    payload: Optional[dict[str, Any]] = None,
) -> bool:
    if not source or not target or source == target:
        return False
    edge_id = f"{edge_type}:{source}->{target}"
    if edge_id in _edge_lookup(graph):
        return False
    graph.setdefault("edges", []).append(
        {
            "id": edge_id,
            "source": source,
            "target": target,
            "type": edge_type,
            "weight": weight,
            "payload": payload or {},
        }
    )
    return True


def _graph_node_type(row: dict[str, Any]) -> str:
    return _as_text(row.get("node_type") or _field(row, "type", "node_type")).lower()


def _graph_label(row: dict[str, Any]) -> str:
    return _first_text(row.get("label"), _field(row, "label", "name", "title", "text"), row.get("node_id"))


def _part_number_from_graph_node(row: dict[str, Any]) -> str:
    explicit = _first_text(
        _field(row, "part_number", "part", "canonical_part_number", "part_id"),
        row.get("label"),
        row.get("node_id"),
    )
    explicit = _strip_known_prefix(explicit, ["part:", "part_number:", "part_number_", "part_"])
    matches = base.extract_part_numbers(explicit, max_parts=1)
    return matches[0] if matches else explicit


def _part_explorer_id(row: dict[str, Any]) -> str:
    return f"part:{_safe_suffix(_part_number_from_graph_node(row), fallback='part')}"


def _nomenclature_label(row: dict[str, Any]) -> str:
    label = _first_text(
        _field(row, "nomenclature", "name", "description", "part_name", "text"),
        row.get("label"),
        row.get("node_id"),
    )
    return _strip_known_prefix(label, ["nomenclature:", "nomenclature_", "name:"])


def _nomenclature_explorer_id(row: dict[str, Any]) -> str:
    raw_id = _first_text(row.get("node_id"), _nomenclature_label(row))
    return f"nomenclature:{_safe_suffix(raw_id, fallback='nomenclature')}"


def _page_explorer_id_from_graph_node(row: dict[str, Any], *, fallback_doc: str) -> str:
    page_id = _first_text(
        _field(row, "page_id", "canonical_page_id", "source_page_id", "document_page_id"),
        row.get("label"),
        row.get("node_id"),
    )
    page_id = _canonical_page_id_any(page_id, fallback_doc=fallback_doc)
    return f"page:{page_id}" if page_id else ""


def _table_exists(conn: Any, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s)", (f"public.{table_name}",))
        row = cur.fetchone()
        return bool(row and row[0])


def _select_all_dicts(conn: Any, table_name: str, *, limit: Optional[int] = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, table_name):
        return []
    sql = f"select * from {table_name}"
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " limit %s"
        params = (limit,)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [desc.name if hasattr(desc, "name") else desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def load_context_v2_rows(database_url: str, *, limit: Optional[int] = None) -> list[dict[str, Any]]:
    try:
        import psycopg  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required. Install with: pip install 'psycopg[binary]'.") from exc
    with psycopg.connect(database_url) as conn:
        return _select_all_dicts(conn, "page_context_v2_records", limit=limit)


def enrich_with_nomenclature(
    graph: dict[str, Any],
    rows: dict[str, list[dict[str, Any]]],
    *,
    fallback_doc: str,
) -> dict[str, int]:
    graph_nodes = rows.get("graph_nodes", [])
    graph_edges = rows.get("graph_edges", [])
    by_graph_id = {_as_text(row.get("node_id")): row for row in graph_nodes if _as_text(row.get("node_id"))}

    added = Counter()

    for edge in graph_edges:
        edge_type = _as_text(edge.get("edge_type"))
        source_row = by_graph_id.get(_as_text(edge.get("source_id")))
        target_row = by_graph_id.get(_as_text(edge.get("target_id")))
        if source_row is None or target_row is None:
            continue
        source_type = _graph_node_type(source_row)
        target_type = _graph_node_type(target_row)

        if edge_type == "HAS_NOMENCLATURE" or {source_type, target_type} == {"part", "nomenclature"}:
            if source_type == "nomenclature" and target_type == "part":
                part_row, nom_row = target_row, source_row
            else:
                part_row, nom_row = source_row, target_row
            if "part" not in _graph_node_type(part_row):
                continue
            part_id = _part_explorer_id(part_row)
            nom_id = _nomenclature_explorer_id(nom_row)
            part_number = _part_number_from_graph_node(part_row)
            nom_label = _nomenclature_label(nom_row)
            if _add_node(
                graph,
                {
                    "id": part_id,
                    "type": "part",
                    "label": part_number,
                    "size": 13,
                    "weight": 1.2,
                    "payload": {
                        "part_number": part_number,
                        "postgres_graph_node_id": part_row.get("node_id"),
                        "source": "graph_nodes.HAS_NOMENCLATURE",
                    },
                },
            ):
                added["part_nodes_from_graph"] += 1
            if _add_node(
                graph,
                {
                    "id": nom_id,
                    "type": "nomenclature",
                    "label": nom_label or "Nomenclature",
                    "size": 11,
                    "weight": 1.1,
                    "payload": {
                        "nomenclature": nom_label,
                        "postgres_graph_node_id": nom_row.get("node_id"),
                        "authority": "part_label_display_only",
                        "source": "graph_nodes.HAS_NOMENCLATURE",
                    },
                },
            ):
                added["nomenclature_nodes_added"] += 1
            if _add_edge(
                graph,
                part_id,
                nom_id,
                "HAS_NOMENCLATURE",
                weight=2.0,
                payload={"postgres_edge_id": edge.get("edge_id"), "source": "graph_edges"},
            ):
                added["has_nomenclature_edges_added"] += 1

        # Keep part-page navigation alive even when the candidate regex part cap hid a part.
        is_part_page = {source_type, target_type} & {"part"} and {source_type, target_type} & {"page"}
        if is_part_page or edge_type in PAGE_PART_EDGE_HINTS:
            if "part" in source_type and "page" in target_type:
                part_row, page_row = source_row, target_row
            elif "page" in source_type and "part" in target_type:
                part_row, page_row = target_row, source_row
            else:
                continue
            part_id = _part_explorer_id(part_row)
            page_id = _page_explorer_id_from_graph_node(page_row, fallback_doc=fallback_doc)
            if part_id and page_id:
                if _add_edge(
                    graph,
                    part_id,
                    page_id,
                    "PART_ON_PAGE",
                    weight=1.5,
                    payload={"postgres_edge_id": edge.get("edge_id"), "source_edge_type": edge_type},
                ):
                    added["part_page_edges_from_graph"] += 1

    return dict(added)


def _context_page_id(row: dict[str, Any], *, fallback_doc: str) -> str:
    page_value = _first_text(
        _field(row, "page_id", "canonical_page_id", "source_page_id", "document_page_id", "page"),
        row.get("page_id"),
        row.get("context_id"),
        row.get("record_id"),
        row.get("id"),
    )
    return _canonical_page_id_any(page_value, fallback_doc=fallback_doc)


def _context_summary(row: dict[str, Any]) -> str:
    return _first_text(
        _field(row, "summary", "context_summary", "short_summary", "page_summary"),
        _field(row, "what_this_page_can_help_answer", "can_help_answer", "answerable_questions"),
        _field(row, "retrieval_cues", "important_entities"),
    )


def _context_record_id(row: dict[str, Any], page_id: str) -> str:
    return _first_text(row.get("context_id"), row.get("record_id"), row.get("id"), f"context_v2:{page_id}")


def _compact_context_payload(row: dict[str, Any], page_id: str) -> dict[str, Any]:
    payload = _as_dict(row.get("payload"))
    result: dict[str, Any] = {
        "page_id": page_id,
        "context_id": _context_record_id(row, page_id),
        "summary": _context_summary(row),
        "authority": _first_text(_field(row, "authority"), "retrieval_helper_only"),
        "can_answer_directly": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "requires_source_citation": True,
    }
    for key in [
        "role",
        "subrole",
        "what_this_page_can_help_answer",
        "answerable_questions",
        "retrieval_cues",
        "important_entities",
        "component_families",
        "nearby_context",
        "source_grounding_phrases",
        "not_good_for_guardrails",
        "guardrails",
        "model",
        "confidence",
    ]:
        value = row.get(key)
        if value in (None, "", [], {}):
            value = payload.get(key)
        if value not in (None, "", [], {}):
            result[key] = value
    return result


def enrich_with_context_v2(
    graph: dict[str, Any],
    context_rows: list[dict[str, Any]],
    *,
    fallback_doc: str,
) -> dict[str, int]:
    added = Counter()
    nodes = _node_lookup(graph)

    for row in context_rows:
        page_id = _context_page_id(row, fallback_doc=fallback_doc)
        if not page_id:
            continue
        page_node_id = f"page:{page_id}"
        if page_node_id not in nodes:
            continue
        context_id_raw = _context_record_id(row, page_id)
        context_node_id = f"page_context_v2:{_safe_suffix(context_id_raw, fallback=page_id)}"
        context_payload = _compact_context_payload(row, page_id)
        summary = context_payload.get("summary") or "PageContextV2"

        if _add_node(
            graph,
            {
                "id": context_node_id,
                "type": "page_context_v2",
                "label": "V2 summary",
                "size": 15,
                "weight": 1.8,
                "payload": context_payload,
            },
        ):
            added["page_context_v2_nodes_added"] += 1

        if _add_edge(
            graph,
            page_node_id,
            context_node_id,
            "HAS_CONTEXT_V2",
            weight=2.2,
            payload={"authority": "retrieval_helper_only", "source": "page_context_v2_records"},
        ):
            added["has_context_v2_edges_added"] += 1

        # Attach the v2 summary directly onto the page node card for quick UI inspection.
        page_payload = nodes[page_node_id].setdefault("payload", {})
        if page_payload.get("context_v2_summary") in (None, "", [], {}):
            page_payload["context_v2_present"] = True
            page_payload["context_v2_summary"] = _as_text(summary)[:1200]
            page_payload["context_v2_authority"] = "retrieval_helper_only"
            added["page_payloads_with_context_v2"] += 1

    return dict(added)


def import_existing_context_v2_graph_nodes(
    graph: dict[str, Any],
    rows: dict[str, list[dict[str, Any]]],
    *,
    fallback_doc: str,
) -> dict[str, int]:
    """Fallback: expose PageContextV2 nodes already present in graph_nodes/graph_edges.

    This covers runs where page_context_v2_records was not selected by the loader but
    HAS_CONTEXT_V2 graph edges were already materialized.
    """
    graph_nodes = rows.get("graph_nodes", [])
    graph_edges = rows.get("graph_edges", [])
    by_graph_id = {_as_text(row.get("node_id")): row for row in graph_nodes if _as_text(row.get("node_id"))}
    added = Counter()

    for edge in graph_edges:
        if _as_text(edge.get("edge_type")) != "HAS_CONTEXT_V2":
            continue
        source_row = by_graph_id.get(_as_text(edge.get("source_id")))
        target_row = by_graph_id.get(_as_text(edge.get("target_id")))
        if source_row is None or target_row is None:
            continue
        source_type = _graph_node_type(source_row)
        target_type = _graph_node_type(target_row)
        if target_type in CONTEXT_V2_NODE_TYPES:
            page_row, context_row = source_row, target_row
        elif source_type in CONTEXT_V2_NODE_TYPES:
            page_row, context_row = target_row, source_row
        else:
            continue
        page_id = _page_explorer_id_from_graph_node(page_row, fallback_doc=fallback_doc)
        context_node_id = f"page_context_v2:{_safe_suffix(context_row.get('node_id'), fallback='context_v2')}"
        summary = _first_text(
            _field(context_row, "summary", "context_summary", "short_summary", "text"),
            context_row.get("label"),
        )
        if _add_node(
            graph,
            {
                "id": context_node_id,
                "type": "page_context_v2",
                "label": "V2 summary",
                "size": 15,
                "weight": 1.8,
                "payload": {
                    "summary": summary,
                    "postgres_graph_node_id": context_row.get("node_id"),
                    "authority": "retrieval_helper_only",
                    "can_answer_directly": False,
                    "canonical_source_truth": False,
                    "requires_source_citation": True,
                    "source": "graph_edges.HAS_CONTEXT_V2",
                },
            },
        ):
            added["page_context_v2_graph_nodes_added"] += 1
        if _add_edge(
            graph,
            page_id,
            context_node_id,
            "HAS_CONTEXT_V2",
            weight=2.2,
            payload={"postgres_edge_id": edge.get("edge_id"), "source": "graph_edges"},
        ):
            added["has_context_v2_graph_edges_added"] += 1

    return dict(added)


def _recompute_summary(graph: dict[str, Any], extras: dict[str, Any]) -> dict[str, Any]:
    node_type_counts = Counter(_as_text(node.get("type")) for node in graph.get("nodes", []))
    edge_type_counts = Counter(_as_text(edge.get("type")) for edge in graph.get("edges", []))
    degree = Counter()
    for edge in graph.get("edges", []):
        degree[_as_text(edge.get("source"))] += 1
        degree[_as_text(edge.get("target"))] += 1
    for node in graph.get("nodes", []):
        node_id = _as_text(node.get("id"))
        if node_id:
            node.setdefault("payload", {})["degree"] = degree.get(node_id, 0)

    summary = dict(graph.get("summary") or {})
    summary.update(
        {
            "status": "OK",
            "version": VERSION,
            "nodes": len(graph.get("nodes", [])),
            "edges": len(graph.get("edges", [])),
            "node_type_counts": dict(sorted(node_type_counts.items())),
            "edge_type_counts": dict(sorted(edge_type_counts.items())),
            "page_nodes": node_type_counts.get("page", 0),
            "part_nodes": node_type_counts.get("part", 0),
            "nomenclature_nodes": node_type_counts.get("nomenclature", 0),
            "page_context_v2_nodes": node_type_counts.get("page_context_v2", 0),
            "candidate_nodes": node_type_counts.get("candidate", 0),
            "citation_nodes": node_type_counts.get("citation", 0),
            "has_nomenclature_edges": edge_type_counts.get("HAS_NOMENCLATURE", 0),
            "has_context_v2_edges": edge_type_counts.get("HAS_CONTEXT_V2", 0),
        }
    )
    summary.update(extras)
    graph["summary"] = summary
    return summary


def _parse_page_range(value: str) -> tuple[int, int] | None:
    text = (value or "").strip()
    if not text:
        return None
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", text)
    if not match:
        raise ValueError("--require-first-pages must look like 1-50")
    start, end = int(match.group(1)), int(match.group(2))
    if start > end:
        start, end = end, start
    return start, end


def _missing_context_v2_pages(graph: dict[str, Any], required_range: str, *, fallback_doc: str) -> list[str]:
    parsed = _parse_page_range(required_range)
    if parsed is None:
        return []
    start, end = parsed
    context_pages = {
        _as_text(edge.get("source"))
        for edge in graph.get("edges", [])
        if _as_text(edge.get("type")) == "HAS_CONTEXT_V2" and _as_text(edge.get("source")).startswith("page:")
    }
    missing = []
    for page_num in range(start, end + 1):
        page_node_id = f"page:{fallback_doc}_p{page_num:06d}"
        if page_node_id not in context_pages:
            missing.append(page_node_id.replace("page:", ""))
    return missing


def write_outputs(graph: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    base.write_json(output_dir / "trace_net_graph_explorer_data.json", graph)
    base.write_json(output_dir / "trace_net_graph_explorer_summary.json", graph["summary"])
    base.write_json(output_dir / "trace_net_graph_explorer_nodes.json", graph["nodes"])
    base.write_json(output_dir / "trace_net_graph_explorer_edges.json", graph["edges"])
    (output_dir / "trace_net_graph_explorer.html").write_text(base.render_html(graph), encoding="utf-8")
    return {
        "html_path": str(output_dir / "trace_net_graph_explorer.html"),
        "data_path": str(output_dir / "trace_net_graph_explorer_data.json"),
        "summary_path": str(output_dir / "trace_net_graph_explorer_summary.json"),
        "nodes_path": str(output_dir / "trace_net_graph_explorer_nodes.json"),
        "edges_path": str(output_dir / "trace_net_graph_explorer_edges.json"),
    }


def build_fixed_graph_explorer(
    database_url: str,
    *,
    output_dir: Path,
    max_part_nodes: int,
    max_parts_per_candidate: int,
    context_v2_limit: Optional[int],
    fallback_doc: str,
    require_first_pages: str,
) -> dict[str, Any]:
    rows = base.load_postgres_rows(database_url)
    graph = base.build_explorer_graph(
        rows,
        max_part_nodes=max_part_nodes,
        max_parts_per_candidate=max_parts_per_candidate,
    )

    context_rows = load_context_v2_rows(database_url, limit=context_v2_limit)
    extras: dict[str, Any] = {
        "context_v2_table_records_read": len(context_rows),
    }
    extras.update({f"nomenclature_{k}": v for k, v in enrich_with_nomenclature(graph, rows, fallback_doc=fallback_doc).items()})
    extras.update({f"context_v2_{k}": v for k, v in enrich_with_context_v2(graph, context_rows, fallback_doc=fallback_doc).items()})
    extras.update({f"context_v2_graph_{k}": v for k, v in import_existing_context_v2_graph_nodes(graph, rows, fallback_doc=fallback_doc).items()})

    missing_pages = _missing_context_v2_pages(graph, require_first_pages, fallback_doc=fallback_doc)
    extras["required_context_v2_page_range"] = require_first_pages
    extras["required_context_v2_missing_pages"] = missing_pages
    extras["required_context_v2_missing_page_count"] = len(missing_pages)

    summary = _recompute_summary(graph, extras)
    paths = write_outputs(graph, output_dir)
    return summary | paths


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build TRACE-Net Graph Explorer with visible Part->Nomenclature and Page->PageContextV2 overlays."
    )
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL", ""))
    parser.add_argument("--output-dir", default=str(base.DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-part-nodes", type=int, default=500)
    parser.add_argument("--max-parts-per-candidate", type=int, default=40)
    parser.add_argument("--context-v2-limit", type=int, default=None)
    parser.add_argument("--fallback-doc", default="t_p_120_1176")
    parser.add_argument("--require-first-pages", default="1-50")
    parser.add_argument("--min-has-nomenclature-edges", type=int, default=1)
    parser.add_argument("--min-context-v2-pages", type=int, default=50)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)

    if not args.database_url:
        print("ERROR: --database-url or TRACE_NET_DATABASE_URL is required", file=sys.stderr)
        return 2

    summary = build_fixed_graph_explorer(
        args.database_url,
        output_dir=Path(args.output_dir),
        max_part_nodes=args.max_part_nodes,
        max_parts_per_candidate=args.max_parts_per_candidate,
        context_v2_limit=args.context_v2_limit,
        fallback_doc=args.fallback_doc,
        require_first_pages=args.require_first_pages,
    )

    print("TRACE-Net graph explorer UI fix")
    print(" Status: OK")
    print(f" Version: {VERSION}")
    print(f" Output dir: {Path(args.output_dir)}")
    for key in [
        "nodes",
        "edges",
        "page_nodes",
        "part_nodes",
        "nomenclature_nodes",
        "page_context_v2_nodes",
        "has_nomenclature_edges",
        "has_context_v2_edges",
        "required_context_v2_missing_page_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(" Node types:", summary.get("node_type_counts"))
    print(" Edge types:", summary.get("edge_type_counts"))
    print("Files written:")
    for key in ["html_path", "data_path", "summary_path", "nodes_path", "edges_path"]:
        print(f" {key}: {summary[key]}")

    failures: list[str] = []
    if int(summary.get("has_nomenclature_edges") or 0) < args.min_has_nomenclature_edges:
        failures.append(
            f"HAS_NOMENCLATURE edges in explorer are below minimum: "
            f"{summary.get('has_nomenclature_edges')} < {args.min_has_nomenclature_edges}"
        )
    if int(summary.get("page_context_v2_nodes") or 0) < args.min_context_v2_pages:
        failures.append(
            f"PageContextV2 nodes in explorer are below minimum: "
            f"{summary.get('page_context_v2_nodes')} < {args.min_context_v2_pages}"
        )
    missing_pages = summary.get("required_context_v2_missing_pages") or []
    if missing_pages:
        preview = ", ".join(missing_pages[:12])
        suffix = "" if len(missing_pages) <= 12 else f" ... {len(missing_pages) - 12} more"
        failures.append(f"Missing HAS_CONTEXT_V2 for required pages: {preview}{suffix}")

    if failures:
        print("Quality check: FAIL", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1

    print("Quality check: PASS")
    if args.open:
        webbrowser.open(Path(summary["html_path"]).resolve().as_uri())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
