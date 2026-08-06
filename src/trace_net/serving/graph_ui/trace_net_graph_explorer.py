from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
import webbrowser
from datetime import date, datetime
from decimal import Decimal
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VERSION = "trace_net_graph_explorer_v1_3_context_overlay"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/graph_explorer")
PART_PATTERNS = [
    re.compile(r"\b\d{3}-\d{5}-\d{3}\b"),
    re.compile(r"\b[A-Z]{1,4}\d{2,6}(?:-[A-Z0-9]{1,6}){1,4}\b"),
]


@dataclass
class ExplorerNode:
    id: str
    type: str
    label: str
    size: int = 12
    weight: float = 1.0
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExplorerEdge:
    id: str
    source: str
    target: str
    type: str
    weight: float = 1.0
    payload: Dict[str, Any] = field(default_factory=dict)


def _json_loads(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _page_num_from_page_id(page_id: str) -> Optional[int]:
    text = _as_text(page_id)
    m = re.search(r"(?:p|page_|zip_page_)(\d{1,6})", text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    m = re.search(r"(\d{6})$", text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def canonical_page_id(page_id: str, fallback_doc: str = "t_p_120_1176") -> str:
    text = _as_text(page_id).strip()
    if not text:
        return text
    if re.search(r"_p\d{6}$", text):
        return text
    num = _page_num_from_page_id(text)
    if num is not None:
        return f"{fallback_doc}_p{num:06d}"
    return text


def extract_part_numbers(text: str, max_parts: int = 50) -> List[str]:
    found: List[str] = []
    seen = set()
    for pattern in PART_PATTERNS:
        for match in pattern.finditer(text or ""):
            part = match.group(0).strip(".,;:()[]{}")
            # Avoid common ATA/page-code-like values with only two digit prefix.
            if re.fullmatch(r"\d{2}-\d{2}(?:-\d{2})?", part):
                continue
            if part not in seen:
                seen.add(part)
                found.append(part)
                if len(found) >= max_parts:
                    return found
    return found


def _node_id(kind: str, raw_id: str) -> str:
    return f"{kind}:{raw_id}"


def _edge_id(source: str, target: str, edge_type: str) -> str:
    return f"{edge_type}:{source}->{target}"


def _add_node(nodes: Dict[str, ExplorerNode], node: ExplorerNode) -> None:
    existing = nodes.get(node.id)
    if existing is None:
        nodes[node.id] = node
        return
    # Merge payloads and keep larger size/weight.
    existing.size = max(existing.size, node.size)
    existing.weight = max(existing.weight, node.weight)
    for key, value in node.payload.items():
        if key not in existing.payload or existing.payload[key] in (None, "", [], {}):
            existing.payload[key] = value


def _add_edge(edges: Dict[str, ExplorerEdge], edge: ExplorerEdge) -> None:
    if edge.id not in edges:
        edges[edge.id] = edge


def _connect(edges: Dict[str, ExplorerEdge], source: str, target: str, edge_type: str, weight: float = 1.0, payload: Optional[Dict[str, Any]] = None) -> None:
    if not source or not target or source == target:
        return
    _add_edge(edges, ExplorerEdge(id=_edge_id(source, target, edge_type), source=source, target=target, type=edge_type, weight=weight, payload=payload or {}))


def _connect_undirected(edges: Dict[str, ExplorerEdge], a: str, b: str, edge_type: str, weight: float = 1.0, payload: Optional[Dict[str, Any]] = None) -> None:
    # Store as deterministic directed edge for rendering; UI treats edges visually as links.
    if a > b:
        a, b = b, a
    _connect(edges, a, b, edge_type, weight, payload)


def _get_table_columns(conn: Any, table_name: str) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public' and table_name = %s
            order by ordinal_position
            """,
            (table_name,),
        )
        return [row[0] for row in cur.fetchall()]


def _table_exists(conn: Any, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s)", (f"public.{table_name}",))
        return cur.fetchone()[0] is not None


def _select_dicts(conn: Any, table_name: str, columns: Sequence[str], limit: Optional[int] = None) -> List[Dict[str, Any]]:
    available = _get_table_columns(conn, table_name)
    cols = [c for c in columns if c in available]
    if not cols:
        return []
    sql = f"select {', '.join(cols)} from {table_name}"
    if limit is not None:
        sql += " limit %s"
        params: Tuple[Any, ...] = (limit,)
    else:
        params = ()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def load_postgres_rows(database_url: str, max_candidates: int = 2500) -> Dict[str, List[Dict[str, Any]]]:
    try:
        import psycopg  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required for --database-url. Install with: pip install 'psycopg[binary]'.") from exc

    rows: Dict[str, List[Dict[str, Any]]] = {}
    with psycopg.connect(database_url) as conn:
        rows["pages"] = _select_dicts(
            conn,
            "pages",
            ["page_id", "document_id", "page_number", "page_label", "ata_code", "source_url", "tiff_path", "ocr_path", "payload"],
        ) if _table_exists(conn, "pages") else []
        rows["ocr_records"] = _select_dicts(
            conn,
            "ocr_records",
            ["page_id", "classification", "status", "chars", "lines", "words", "part_like_count", "ocr_path", "text", "payload"],
        ) if _table_exists(conn, "ocr_records") else []
        rows["rag_candidate_chunks"] = _select_dicts(
            conn,
            "rag_candidate_chunks",
            ["candidate_id", "page_id", "candidate_type", "rag_bucket", "evidence_layer", "trust_tier", "usable_confidence", "text", "source_url", "tiff_path", "ocr_path", "payload"],
            limit=max_candidates,
        ) if _table_exists(conn, "rag_candidate_chunks") else []
        rows["source_citations"] = _select_dicts(
            conn,
            "source_citations",
            ["citation_id", "candidate_id", "page_id", "source_url", "tiff_path", "ocr_path", "citation_text", "payload"],
        ) if _table_exists(conn, "source_citations") else []
        rows["page_trust_traits"] = _select_dicts(
            conn,
            "page_trust_traits",
            ["trait_id", "page_id", "evidence_layer", "trust_tier", "rag_action", "usable_confidence", "payload"],
        ) if _table_exists(conn, "page_trust_traits") else []
        rows["page_context_records"] = _select_dicts(
            conn,
            "page_context_records",
            ["context_id", "page_id", "page_id_resolved", "page_number", "role", "summary", "topics", "highlighted_parts", "confidence", "confidence_score", "context_model", "prompt_version", "trust_scope", "rag_role", "can_answer_directly", "can_support_answer", "requires_citation", "canonical_source_truth", "payload"],
        ) if _table_exists(conn, "page_context_records") else []
        rows["page_context_topics"] = _select_dicts(
            conn,
            "page_context_topics",
            ["context_id", "page_id", "topic", "payload"],
        ) if _table_exists(conn, "page_context_topics") else []
        rows["page_context_highlighted_parts"] = _select_dicts(
            conn,
            "page_context_highlighted_parts",
            ["context_id", "page_id", "part_number", "payload"],
        ) if _table_exists(conn, "page_context_highlighted_parts") else []
        rows["graph_nodes"] = _select_dicts(conn, "graph_nodes", ["node_id", "node_type", "label", "payload"], limit=200000) if _table_exists(conn, "graph_nodes") else []
        rows["graph_edges"] = _select_dicts(conn, "graph_edges", ["edge_id", "source_id", "target_id", "edge_type", "payload"], limit=300000) if _table_exists(conn, "graph_edges") else []
    return rows


def build_explorer_graph(
    rows: Dict[str, List[Dict[str, Any]]],
    max_part_nodes: int = 500,
    max_parts_per_candidate: int = 40,
) -> Dict[str, Any]:
    nodes: Dict[str, ExplorerNode] = {}
    edges: Dict[str, ExplorerEdge] = {}
    page_alias: Dict[str, str] = {}
    page_by_canonical: Dict[str, Dict[str, Any]] = {}
    fallback_doc = "t_p_120_1176"

    # Pages are the primary hubs.
    for row in rows.get("pages", []):
        raw_page_id = _as_text(row.get("page_id"))
        page_id = canonical_page_id(raw_page_id, fallback_doc=fallback_doc)
        if not page_id:
            continue
        page_alias[raw_page_id] = page_id
        page_by_canonical[page_id] = row
        label = page_id.split("_p")[-1] if "_p" in page_id else page_id
        _add_node(
            nodes,
            ExplorerNode(
                id=_node_id("page", page_id),
                type="page",
                label=f"Page {label}",
                size=24,
                weight=3.0,
                payload={
                    "page_id": page_id,
                    "raw_page_id": raw_page_id,
                    "document_id": row.get("document_id"),
                    "page_number": row.get("page_number"),
                    "page_label": row.get("page_label"),
                    "ata_code": row.get("ata_code"),
                    "source_url": row.get("source_url"),
                    "tiff_path": row.get("tiff_path"),
                    "ocr_path": row.get("ocr_path"),
                },
            ),
        )
        if row.get("source_url"):
            source_id = _node_id("source", page_id)
            _add_node(nodes, ExplorerNode(source_id, "source", "Source link", size=10, payload={"source_url": row.get("source_url")}))
            _connect(edges, _node_id("page", page_id), source_id, "HAS_SOURCE", 2.0)
        if row.get("ocr_path"):
            ocr_id = _node_id("ocr", page_id)
            _add_node(nodes, ExplorerNode(ocr_id, "ocr", "OCR", size=10, payload={"ocr_path": row.get("ocr_path")}))
            _connect(edges, _node_id("page", page_id), ocr_id, "HAS_OCR", 1.5)
        if row.get("tiff_path"):
            tiff_id = _node_id("tiff", page_id)
            _add_node(nodes, ExplorerNode(tiff_id, "tiff", "TIFF", size=10, payload={"tiff_path": row.get("tiff_path")}))
            _connect(edges, _node_id("page", page_id), tiff_id, "HAS_TIFF", 1.5)

    # Page context overlay: semantic helper nodes, not source truth.
    # These records are collapsed local graph helpers. They connect pages to summaries,
    # topics, and highlighted parts so users can jump between semantic context and
    # source-backed page/candidate evidence.
    context_topics: Dict[str, List[str]] = defaultdict(list)
    for topic_row in rows.get("page_context_topics", []):
        cid = _as_text(topic_row.get("context_id"))
        topic = _as_text(topic_row.get("topic"))
        if cid and topic and topic not in context_topics[cid]:
            context_topics[cid].append(topic)

    context_parts: Dict[str, List[str]] = defaultdict(list)
    for part_row in rows.get("page_context_highlighted_parts", []):
        cid = _as_text(part_row.get("context_id"))
        part = _as_text(part_row.get("part_number"))
        if cid and part and part not in context_parts[cid]:
            context_parts[cid].append(part)

    for row in rows.get("page_context_records", []):
        raw_page_id = _as_text(row.get("page_id_resolved") or row.get("page_id"))
        page_id = canonical_page_id(raw_page_id, fallback_doc=fallback_doc)
        page_node = _node_id("page", page_id)
        if page_node not in nodes:
            continue
        context_id = _as_text(row.get("context_id")) or _node_id("page_context", page_id)
        if not context_id.startswith("page_context:"):
            context_id = _node_id("page_context", context_id)
        role = _as_text(row.get("role") or "context")
        summary_text = _as_text(row.get("summary"))
        confidence = _as_text(row.get("confidence") or "unknown")
        topics_value = _json_loads(row.get("topics")) or []
        highlighted_value = _json_loads(row.get("highlighted_parts")) or []
        topics = list(context_topics.get(context_id, [])) or [str(t) for t in topics_value if str(t).strip()]
        highlighted_parts = list(context_parts.get(context_id, [])) or [str(p) for p in highlighted_value if str(p).strip()]
        label = f"Context: {role}"
        _add_node(
            nodes,
            ExplorerNode(
                id=context_id,
                type="page_context",
                label=label,
                size=16,
                weight=1.6,
                payload={
                    "context_id": context_id,
                    "page_id": page_id,
                    "role": role,
                    "summary": summary_text,
                    "topics": topics[:30],
                    "highlighted_parts": highlighted_parts[:40],
                    "confidence": confidence,
                    "confidence_score": row.get("confidence_score"),
                    "context_model": row.get("context_model"),
                    "prompt_version": row.get("prompt_version"),
                    "trust_scope": row.get("trust_scope"),
                    "rag_role": row.get("rag_role"),
                    "can_answer_directly": row.get("can_answer_directly"),
                    "can_support_answer": row.get("can_support_answer"),
                    "requires_citation": row.get("requires_citation"),
                    "canonical_source_truth": row.get("canonical_source_truth"),
                },
            ),
        )
        _connect(edges, page_node, context_id, "HAS_CONTEXT", 2.0)
        _connect(edges, context_id, page_node, "SUMMARIZES", 0.8)

        if role:
            role_node = _node_id("page_role", role)
            _add_node(nodes, ExplorerNode(role_node, "page_role", role, size=14, payload={"role": role}))
            _connect(edges, context_id, role_node, "HAS_ROLE", 0.8)

        for topic in topics[:20]:
            topic_id = _node_id("topic", topic.lower().strip())
            _add_node(nodes, ExplorerNode(topic_id, "topic", topic, size=10, weight=0.7, payload={"topic": topic}))
            _connect(edges, context_id, topic_id, "TAGGED_AS", 0.7)
            _connect(edges, page_node, topic_id, "PAGE_TAGGED_AS", 0.25)

        for part in highlighted_parts[:max_parts_per_candidate]:
            part_node = _node_id("part", part)
            _add_node(nodes, ExplorerNode(part_node, "part", part, size=9, weight=0.8, payload={"part_number": part, "from_page_context": True}))
            _connect(edges, context_id, part_node, "HIGHLIGHTS_PART", 1.0)
            _connect(edges, part_node, page_node, "CONTEXT_PART_ON_PAGE", 0.9)

    # OCR classifications.
    for row in rows.get("ocr_records", []):
        page_id = canonical_page_id(_as_text(row.get("page_id")), fallback_doc=fallback_doc)
        page_node = _node_id("page", page_id)
        if page_node not in nodes:
            continue
        classification = _as_text(row.get("classification") or "unknown")
        class_node = _node_id("ocr_class", classification)
        _add_node(nodes, ExplorerNode(class_node, "ocr_class", classification, size=14, payload={"classification": classification}))
        _connect(edges, page_node, class_node, "HAS_OCR_CLASS", 0.8)
        ocr_node = _node_id("ocr", page_id)
        if ocr_node in nodes:
            nodes[ocr_node].payload.update({
                "classification": row.get("classification"),
                "status": row.get("status"),
                "chars": row.get("chars"),
                "lines": row.get("lines"),
                "words": row.get("words"),
                "part_like_count": row.get("part_like_count"),
                "text_preview": _as_text(row.get("text"))[:600],
            })

    # Trust traits.
    for row in rows.get("page_trust_traits", []):
        page_id = canonical_page_id(_as_text(row.get("page_id")), fallback_doc=fallback_doc)
        page_node = _node_id("page", page_id)
        if page_node not in nodes:
            continue
        layer = _as_text(row.get("evidence_layer") or "unknown")
        tier = _as_text(row.get("trust_tier") or "unknown")
        trait_id = _node_id("trust", f"{layer}:{tier}")
        _add_node(nodes, ExplorerNode(trait_id, "trust", f"{layer} {tier}", size=14, payload={"evidence_layer": layer, "trust_tier": tier, "rag_action": row.get("rag_action")}))
        _connect(edges, page_node, trait_id, "HAS_TRUST_TRAIT", 1.2, {"confidence": row.get("usable_confidence")})

    # Candidate chunks and bucket/layer/trust links.
    candidate_rows = rows.get("rag_candidate_chunks", [])
    part_counter: Counter[str] = Counter()
    candidate_parts: Dict[str, List[str]] = {}
    for row in candidate_rows:
        candidate_id = _as_text(row.get("candidate_id")) or f"candidate_{len(candidate_parts)+1}"
        parts = extract_part_numbers(_as_text(row.get("text")), max_parts=max_parts_per_candidate)
        candidate_parts[candidate_id] = parts
        part_counter.update(parts)

    allowed_parts = {part for part, _count in part_counter.most_common(max_part_nodes)}

    for row in candidate_rows:
        candidate_id = _as_text(row.get("candidate_id")) or f"candidate_{len(nodes)}"
        page_id = canonical_page_id(_as_text(row.get("page_id")), fallback_doc=fallback_doc)
        page_node = _node_id("page", page_id)
        if page_node not in nodes:
            # Try page number aliases if candidate uses t_p while pages use zip or vice versa.
            num = _page_num_from_page_id(_as_text(row.get("page_id")))
            if num is not None:
                page_id = f"{fallback_doc}_p{num:06d}"
                page_node = _node_id("page", page_id)
        if page_node not in nodes:
            continue
        bucket = _as_text(row.get("rag_bucket") or row.get("candidate_type") or "candidate")
        layer = _as_text(row.get("evidence_layer") or "unknown")
        trust = _as_text(row.get("trust_tier") or "")
        cand_node = _node_id("candidate", candidate_id)
        label = bucket.replace("_", " ")
        _add_node(
            nodes,
            ExplorerNode(
                cand_node,
                "candidate",
                label,
                size=13,
                weight=1.5,
                payload={
                    "candidate_id": candidate_id,
                    "page_id": page_id,
                    "rag_bucket": bucket,
                    "evidence_layer": layer,
                    "trust_tier": trust,
                    "usable_confidence": row.get("usable_confidence"),
                    "source_url": row.get("source_url"),
                    "tiff_path": row.get("tiff_path"),
                    "ocr_path": row.get("ocr_path"),
                    "text_preview": _as_text(row.get("text"))[:900],
                },
            ),
        )
        _connect(edges, page_node, cand_node, "HAS_CANDIDATE", 2.0)

        bucket_node = _node_id("bucket", bucket)
        _add_node(nodes, ExplorerNode(bucket_node, "bucket", bucket, size=17, payload={"rag_bucket": bucket}))
        _connect(edges, cand_node, bucket_node, "IN_BUCKET", 1.0)

        layer_node = _node_id("layer", layer)
        _add_node(nodes, ExplorerNode(layer_node, "layer", layer, size=15, payload={"evidence_layer": layer}))
        _connect(edges, cand_node, layer_node, "HAS_LAYER", 0.8)

        if trust:
            trust_node = _node_id("trust_tier", trust)
            _add_node(nodes, ExplorerNode(trust_node, "trust_tier", f"Trust {trust}", size=16, payload={"trust_tier": trust}))
            _connect(edges, cand_node, trust_node, "HAS_TRUST_TIER", 0.8)

        for part in candidate_parts.get(candidate_id, []):
            if part not in allowed_parts:
                continue
            part_node = _node_id("part", part)
            _add_node(nodes, ExplorerNode(part_node, "part", part, size=9, weight=0.8, payload={"part_number": part, "frequency": part_counter.get(part, 0)}))
            _connect(edges, cand_node, part_node, "MENTIONS_PART", 1.1)
            _connect(edges, part_node, page_node, "PART_ON_PAGE", 1.5)

    # Citations.
    for row in rows.get("source_citations", []):
        citation_id = _as_text(row.get("citation_id"))
        if not citation_id:
            continue
        page_id = canonical_page_id(_as_text(row.get("page_id")), fallback_doc=fallback_doc)
        page_node = _node_id("page", page_id)
        if page_node not in nodes:
            continue
        cit_node = _node_id("citation", citation_id)
        _add_node(nodes, ExplorerNode(cit_node, "citation", "Citation", size=9, payload={"citation_id": citation_id, "source_url": row.get("source_url"), "tiff_path": row.get("tiff_path"), "ocr_path": row.get("ocr_path"), "citation_text": _as_text(row.get("citation_text"))[:500]}))
        _connect(edges, page_node, cit_node, "HAS_CITATION", 0.8)
        cand_id = _as_text(row.get("candidate_id"))
        if cand_id:
            cand_node = _node_id("candidate", cand_id)
            if cand_node in nodes:
                _connect(edges, cand_node, cit_node, "CITED_BY", 0.8)

    # Light page order links for navigation.
    page_nodes = sorted([n for n in nodes.values() if n.type == "page"], key=lambda n: (_page_num_from_page_id(n.payload.get("page_id", n.id)) or 10**9))
    for a, b in zip(page_nodes, page_nodes[1:]):
        _connect(edges, a.id, b.id, "NEXT_PAGE", 0.2)

    degree: Counter[str] = Counter()
    for edge in edges.values():
        degree[edge.source] += 1
        degree[edge.target] += 1
    for node_id, deg in degree.items():
        if node_id in nodes:
            nodes[node_id].payload["degree"] = deg
            if nodes[node_id].type == "part":
                nodes[node_id].size = min(24, 8 + int(math.sqrt(max(deg, 1)) * 2))
            elif nodes[node_id].type == "page":
                nodes[node_id].size = min(34, 22 + int(math.sqrt(max(deg, 1))))

    node_list = [node.__dict__ for node in nodes.values()]
    edge_list = [edge.__dict__ for edge in edges.values()]
    type_counts = Counter(n["type"] for n in node_list)
    edge_type_counts = Counter(e["type"] for e in edge_list)
    summary = {
        "status": "OK",
        "version": VERSION,
        "nodes": len(node_list),
        "edges": len(edge_list),
        "node_type_counts": dict(sorted(type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "page_nodes": type_counts.get("page", 0),
        "part_nodes": type_counts.get("part", 0),
        "candidate_nodes": type_counts.get("candidate", 0),
        "citation_nodes": type_counts.get("citation", 0),
        "page_context_nodes": type_counts.get("page_context", 0),
        "topic_nodes": type_counts.get("topic", 0),
        "max_part_nodes": max_part_nodes,
        "max_parts_per_candidate": max_parts_per_candidate,
    }
    return {"version": VERSION, "summary": summary, "nodes": node_list, "edges": edge_list}


def _json_default(value: Any) -> Any:
    """Convert Postgres/Python values to JSON-safe values for the browser artifact.

    psycopg returns NUMERIC columns as Decimal, and JSONB payloads can also carry
    Decimal values after row materialization.  The graph explorer is a read-only
    UI artifact, so converting Decimal to float is appropriate for scores such as
    usable_confidence.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")


def render_html(graph: Dict[str, Any]) -> str:
    data_json = json.dumps({"nodes": graph["nodes"], "edges": graph["edges"], "summary": graph["summary"]}, ensure_ascii=False, default=_json_default)
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>TRACE-Net Graph Explorer</title>
<style>
  :root {{ --bg:#0f172a; --panel:#111827; --text:#e5e7eb; --muted:#94a3b8; --accent:#38bdf8; --border:#334155; }}
  body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background:var(--bg); color:var(--text); overflow:hidden; }}
  #app {{ display:grid; grid-template-columns: 360px 1fr; height:100vh; }}
  #side {{ background:var(--panel); border-right:1px solid var(--border); padding:14px; overflow:auto; }}
  #main {{ position:relative; }}
  canvas {{ width:100%; height:100%; display:block; background: radial-gradient(circle at 50% 30%, #1e293b, #020617 72%); }}
  h1 {{ font-size:18px; margin:0 0 4px; }}
  h2 {{ font-size:13px; color:var(--muted); margin:18px 0 8px; text-transform:uppercase; letter-spacing:.06em; }}
  .small {{ color:var(--muted); font-size:12px; line-height:1.35; }}
  .row {{ display:flex; gap:8px; align-items:center; margin:8px 0; }}
  input, select, button {{ background:#0b1220; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px; }}
  input {{ flex:1; width:100%; box-sizing:border-box; }}
  button {{ cursor:pointer; }}
  button:hover {{ border-color:var(--accent); }}
  .pill {{ display:inline-block; padding:3px 7px; border-radius:999px; background:#1f2937; color:#cbd5e1; margin:2px 3px 2px 0; font-size:12px; }}
  .list button {{ display:block; width:100%; text-align:left; margin:3px 0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .kv {{ display:grid; grid-template-columns: 110px 1fr; gap:4px 8px; font-size:12px; }}
  .kv div:nth-child(odd) {{ color:var(--muted); }}
  pre {{ white-space:pre-wrap; font-size:11px; background:#020617; border:1px solid var(--border); border-radius:8px; padding:8px; max-height:220px; overflow:auto; }}
  #toolbar {{ position:absolute; top:12px; right:12px; display:flex; gap:8px; }}
  #tooltip {{ position:absolute; pointer-events:none; background:#111827; border:1px solid var(--border); color:var(--text); padding:7px 9px; border-radius:8px; font-size:12px; display:none; max-width:360px; }}
  .legend-dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; }}
</style>
</head>
<body>
<div id=\"app\">
  <aside id=\"side\">
    <h1>TRACE-Net Graph Explorer</h1>
    <div class=\"small\">Click any node to recenter. This is a graph overlay, not a tree: parts, pages, citations, candidates, trust tiers, OCR, and sources cross-link directly.</div>
    <h2>Search</h2>
    <div class=\"row\"><input id=\"search\" placeholder=\"part, page, bucket, trust...\" /><button id=\"go\">Go</button></div>
    <div id=\"searchResults\" class=\"list\"></div>
    <h2>View</h2>
    <div class=\"row\">
      <label class=\"small\">Depth</label>
      <select id=\"depth\"><option value=\"1\">1 hop</option><option value=\"2\" selected>2 hops</option></select>
      <button id=\"back\">Back</button><button id=\"reset\">Reset</button>
    </div>
    <div id=\"stats\" class=\"small\"></div>
    <h2>Selected node</h2>
    <div id=\"selected\" class=\"small\">None selected.</div>
    <h2>Neighbors</h2>
    <div id=\"neighbors\" class=\"list\"></div>
    <h2>Legend</h2>
    <div id=\"legend\" class=\"small\"></div>
  </aside>
  <main id=\"main\"><canvas id=\"canvas\"></canvas><div id=\"toolbar\"><button id=\"fit\">Fit</button></div><div id=\"tooltip\"></div></main>
</div>
<script>
const GRAPH = {data_json};
const nodes = new Map(GRAPH.nodes.map(n => [n.id, n]));
const edges = GRAPH.edges;
const adj = new Map();
for (const n of nodes.values()) adj.set(n.id, []);
for (const e of edges) {{
  if (!adj.has(e.source)) adj.set(e.source, []);
  if (!adj.has(e.target)) adj.set(e.target, []);
  adj.get(e.source).push({{id:e.target, edge:e}});
  adj.get(e.target).push({{id:e.source, edge:e}});
}}
const colors = {{
  page:'#38bdf8', part:'#facc15', candidate:'#a78bfa', bucket:'#34d399', layer:'#22c55e', trust:'#fb7185', trust_tier:'#f472b6', citation:'#f97316', source:'#60a5fa', ocr:'#cbd5e1', tiff:'#94a3b8', ocr_class:'#818cf8'
}};
let selectedId = findDefaultNode();
let history = [];
let positions = new Map();
let visible = {{nodes:[], edges:[]}};
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const tooltip = document.getElementById('tooltip');
let scale = 1, offsetX = 0, offsetY = 0;
let dragging = false, dragStart = null;

function findDefaultNode() {{
  const part = [...nodes.values()].find(n => n.type === 'part' && n.label.includes('120-50645-009'));
  if (part) return part.id;
  const page = [...nodes.values()].find(n => n.type === 'page');
  return page ? page.id : [...nodes.keys()][0];
}}
function neighborhood(root, depth) {{
  const seen = new Set([root]);
  let frontier = [root];
  for (let d=0; d<depth; d++) {{
    const next = [];
    for (const id of frontier) {{
      for (const nb of adj.get(id) || []) {{
        if (!seen.has(nb.id)) {{ seen.add(nb.id); next.push(nb.id); }}
      }}
    }}
    frontier = next;
  }}
  const nlist = [...seen].map(id => nodes.get(id)).filter(Boolean);
  const eset = edges.filter(e => seen.has(e.source) && seen.has(e.target));
  return {{nodes:nlist, edges:eset}};
}}
function layoutVisible() {{
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const cx = w/2, cy = h/2;
  positions.clear();
  const root = nodes.get(selectedId);
  positions.set(selectedId, {{x:cx, y:cy}});
  const byType = {{}};
  for (const n of visible.nodes) if (n.id !== selectedId) (byType[n.type] ||= []).push(n);
  const order = ['page','part','candidate','bucket','source','ocr','tiff','citation','trust','trust_tier','layer','ocr_class'];
  let ring = 0;
  for (const type of order.concat(Object.keys(byType).filter(t => !order.includes(t)))) {{
    const arr = byType[type] || [];
    if (!arr.length) continue;
    ring++;
    const r = Math.min(Math.min(w,h)*0.42, 110 + ring*72);
    const start = (ring * 0.67) % (Math.PI*2);
    arr.sort((a,b)=> (b.payload?.degree||0)-(a.payload?.degree||0));
    arr.forEach((n,i)=>{{
      const angle = start + (i/Math.max(arr.length,1))*Math.PI*2;
      const jitter = (i%3-1)*10;
      positions.set(n.id, {{x:cx + Math.cos(angle)*(r+jitter), y:cy + Math.sin(angle)*(r+jitter)}});
    }});
  }}
}}
function updateView(pushHist=true) {{
  if (pushHist && history[history.length-1] !== selectedId) history.push(selectedId);
  const depth = Number(document.getElementById('depth').value || 2);
  visible = neighborhood(selectedId, depth);
  layoutVisible();
  updateSide();
  draw();
}}
function updateSide() {{
  const s = GRAPH.summary;
  document.getElementById('stats').innerHTML = `Total graph: <b>${{s.nodes}}</b> nodes, <b>${{s.edges}}</b> edges<br/>Visible: <b>${{visible.nodes.length}}</b> nodes, <b>${{visible.edges.length}}</b> edges`;
  const n = nodes.get(selectedId);
  if (!n) return;
  const pills = `<span class=\"pill\">${{escapeHtml(n.type)}}</span><span class=\"pill\">degree ${{(n.payload&&n.payload.degree)||0}}</span>`;
  const payloadRows = Object.entries(n.payload||{{}}).slice(0, 22).map(([k,v]) => `<div>${{escapeHtml(k)}}</div><div>${{escapeHtml(formatVal(v))}}</div>`).join('');
  document.getElementById('selected').innerHTML = `<b>${{escapeHtml(n.label)}}</b><br/>${{pills}}<div class=\"kv\">${{payloadRows}}</div>`;
  const nbs = (adj.get(selectedId)||[]).map(x => nodes.get(x.id)).filter(Boolean).sort((a,b)=>a.type.localeCompare(b.type)||a.label.localeCompare(b.label)).slice(0,160);
  const neighborEl = document.getElementById('neighbors');
  neighborEl.innerHTML = nbs.map(nodeButton).join('') || '<span class=\"small\">No neighbors.</span>';
  wireNodeButtons(neighborEl);
  const types = Object.entries(GRAPH.summary.node_type_counts||{{}}).map(([t,c])=>`<span class=\"legend-dot\" style=\"background:${{colors[t]||'#fff'}}\"></span>${{escapeHtml(t)}} (${{c}})`).join('<br/>');
  document.getElementById('legend').innerHTML = types;
}}
function draw() {{
  const dpr = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * dpr; canvas.height = canvas.clientHeight * dpr;
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,canvas.clientWidth,canvas.clientHeight);
  ctx.save(); ctx.translate(offsetX, offsetY); ctx.scale(scale, scale);
  for (const e of visible.edges) {{
    const a = positions.get(e.source), b = positions.get(e.target); if (!a||!b) continue;
    ctx.strokeStyle = 'rgba(148,163,184,0.34)'; ctx.lineWidth = Math.max(0.5, e.weight||1);
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
  }}
  for (const n of visible.nodes) {{
    const p = positions.get(n.id); if (!p) continue;
    const r = n.id===selectedId ? (n.size||12)+5 : (n.size||12);
    ctx.fillStyle = colors[n.type] || '#f8fafc';
    ctx.beginPath(); ctx.arc(p.x,p.y,r,0,Math.PI*2); ctx.fill();
    ctx.strokeStyle = n.id===selectedId ? '#ffffff' : 'rgba(15,23,42,0.9)'; ctx.lineWidth = n.id===selectedId ? 3 : 1.5; ctx.stroke();
    if (r >= 12) {{
      ctx.font = '12px system-ui'; ctx.fillStyle = '#e5e7eb'; ctx.textAlign = 'center';
      const text = n.label.length > 22 ? n.label.slice(0,21)+'…' : n.label;
      ctx.fillText(text, p.x, p.y + r + 14);
    }}
  }}
  ctx.restore();
}}
function nodeAt(x,y) {{
  const tx = (x-offsetX)/scale, ty = (y-offsetY)/scale;
  let best = null, bestD = Infinity;
  for (const n of visible.nodes) {{
    const p = positions.get(n.id); if (!p) continue;
    const r = (n.size||12)+8;
    const d = Math.hypot(tx-p.x, ty-p.y);
    if (d < r && d < bestD) {{ best=n; bestD=d; }}
  }}
  return best;
}}
function selectNode(id) {{ selectedId=id; updateView(true); }}
window.selectNode = selectNode;
canvas.addEventListener('click', ev => {{ const n=nodeAt(ev.offsetX,ev.offsetY); if(n) selectNode(n.id); }});
canvas.addEventListener('mousemove', ev => {{ const n=nodeAt(ev.offsetX,ev.offsetY); if(n) {{ tooltip.style.display='block'; tooltip.style.left=(ev.offsetX+14)+'px'; tooltip.style.top=(ev.offsetY+14)+'px'; tooltip.innerHTML=`<b>${{escapeHtml(n.label)}}</b><br/>${{escapeHtml(n.type)}}`; }} else tooltip.style.display='none'; }});
canvas.addEventListener('wheel', ev => {{ ev.preventDefault(); const factor=ev.deltaY<0?1.1:0.9; scale=Math.max(.3, Math.min(3, scale*factor)); draw(); }});
canvas.addEventListener('mousedown', ev => {{ dragging=true; dragStart={{x:ev.clientX-offsetX,y:ev.clientY-offsetY}}; }});
window.addEventListener('mouseup',()=>dragging=false);
window.addEventListener('mousemove',ev=>{{ if(dragging){{ offsetX=ev.clientX-dragStart.x; offsetY=ev.clientY-dragStart.y; draw(); }} }});
window.addEventListener('resize',()=>{{layoutVisible();draw();}});
document.getElementById('depth').addEventListener('change',()=>updateView(false));
document.getElementById('reset').addEventListener('click',()=>{{scale=1;offsetX=0;offsetY=0;selectedId=findDefaultNode();updateView(false);}});
document.getElementById('fit').addEventListener('click',()=>{{scale=1;offsetX=0;offsetY=0;draw();}});
document.getElementById('back').addEventListener('click',()=>{{ if(history.length>1){{ history.pop(); selectedId=history[history.length-1]; updateView(false); }} }});
document.getElementById('go').addEventListener('click',search);
document.getElementById('search').addEventListener('keydown',ev=>{{if(ev.key==='Enter')search();}});
function search() {{
  const q = document.getElementById('search').value.toLowerCase().trim();
  const out = document.getElementById('searchResults');
  if(!q) {{out.innerHTML='';return;}}
  const hits = [...nodes.values()].filter(n => (n.label||'').toLowerCase().includes(q) || n.id.toLowerCase().includes(q) || JSON.stringify(n.payload||{{}}).toLowerCase().includes(q)).slice(0,30);
  out.innerHTML = hits.map(nodeButton).join('') || '<span class=\"small\">No matches.</span>';
  wireNodeButtons(out);
}}
function escapeHtml(s) {{ return String(s??'').replace(/[&<>\"]/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[ch])); }}
function escapeAttr(s) {{ return String(s??'').replace(/[&<>\"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[ch])); }}
function nodeButton(n) {{ return `<button data-node-id=\"${{escapeAttr(n.id)}}\">${{escapeHtml(n.type)}} · ${{escapeHtml(n.label)}}</button>`; }}
function wireNodeButtons(root) {{ root.querySelectorAll('button[data-node-id]').forEach(btn => {{ btn.onclick = () => selectNode(btn.dataset.nodeId); }}); }}
function formatVal(v) {{ if(v===null||v===undefined) return ''; if(typeof v==='object') return JSON.stringify(v).slice(0,180); return String(v).slice(0,260); }}
updateView(false);
</script>
</body>
</html>"""


def build_graph_explorer(database_url: str, output_dir: Path = DEFAULT_OUTPUT_DIR, max_part_nodes: int = 500, max_parts_per_candidate: int = 40) -> Dict[str, Any]:
    rows = load_postgres_rows(database_url)
    graph = build_explorer_graph(rows, max_part_nodes=max_part_nodes, max_parts_per_candidate=max_parts_per_candidate)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "trace_net_graph_explorer_data.json", graph)
    write_json(output_dir / "trace_net_graph_explorer_summary.json", graph["summary"])
    write_json(output_dir / "trace_net_graph_explorer_nodes.json", graph["nodes"])
    write_json(output_dir / "trace_net_graph_explorer_edges.json", graph["edges"])
    (output_dir / "trace_net_graph_explorer.html").write_text(render_html(graph), encoding="utf-8")
    return graph["summary"] | {
        "data_path": str(output_dir / "trace_net_graph_explorer_data.json"),
        "html_path": str(output_dir / "trace_net_graph_explorer.html"),
        "nodes_path": str(output_dir / "trace_net_graph_explorer_nodes.json"),
        "edges_path": str(output_dir / "trace_net_graph_explorer_edges.json"),
        "summary_path": str(output_dir / "trace_net_graph_explorer_summary.json"),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build a local interactive TRACE-Net graph explorer HTML from PostgreSQL.")
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL", ""), help="PostgreSQL URL. Defaults to TRACE_NET_DATABASE_URL.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-part-nodes", type=int, default=500)
    parser.add_argument("--max-parts-per-candidate", type=int, default=40)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)
    if not args.database_url:
        print("ERROR: --database-url or TRACE_NET_DATABASE_URL is required", file=sys.stderr)
        return 2
    summary = build_graph_explorer(args.database_url, output_dir=Path(args.output_dir), max_part_nodes=args.max_part_nodes, max_parts_per_candidate=args.max_parts_per_candidate)
    print("TRACE-Net graph explorer")
    print("  Status: OK")
    print(f"  Version: {VERSION}")
    print(f"  Output dir: {Path(args.output_dir)}")
    print("  Summary:")
    for key in ["nodes", "edges", "page_nodes", "part_nodes", "candidate_nodes", "citation_nodes"]:
        print(f"    {key}: {summary.get(key)}")
    print("  Node types:", summary.get("node_type_counts"))
    print("Files written:")
    print(f"  html: {summary['html_path']}")
    print(f"  data: {summary['data_path']}")
    print(f"  summary: {summary['summary_path']}")
    if args.open:
        webbrowser.open(Path(summary["html_path"]).resolve().as_uri())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
