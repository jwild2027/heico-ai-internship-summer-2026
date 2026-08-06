from __future__ import annotations

import argparse
import hashlib
import json
import re
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

VERSION = "trace_net_page_context_overlay_v1"
DEFAULT_CONTEXT_FILE = Path("local_data/organization/context/page_contexts.json")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/page_context_overlay")


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    return str(value)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, default=_json_default) + "\n")


def slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    if not text:
        text = "unknown"
    return text[:96]


def parse_page_number(page_id: str) -> int | None:
    if not page_id:
        return None
    patterns = [r"p(\d{6})$", r"zip_page_(\d{6})$", r"_(\d{6})$", r"(\d{1,6})$"]
    for pattern in patterns:
        m = re.search(pattern, page_id)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
    return None


def canonical_page_id(page_id: str) -> str:
    page_id = str(page_id or "").strip()
    if re.match(r"^t_p_\d+_\d+_p\d{6}$", page_id):
        return page_id
    num = parse_page_number(page_id)
    if num is not None:
        return f"t_p_120_1176_p{num:06d}"
    return page_id


def page_aliases(page_id: str) -> list[str]:
    page_id = str(page_id or "").strip()
    aliases = []
    if page_id:
        aliases.append(page_id)
    num = parse_page_number(page_id)
    if num is not None:
        aliases.extend([
            f"t_p_120_1176_p{num:06d}",
            f"zip_page_{num:06d}",
            f"page:t_p_120_1176_p{num:06d}",
            f"page:zip_page_{num:06d}",
        ])
    out = []
    seen = set()
    for item in aliases:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        # Keep comma-separated topic strings useful, while preserving part-number strings.
        if "," in value:
            return [v.strip() for v in value.split(",") if v.strip()]
        return [value] if value.strip() else []
    return [value]




PART_LIKE_RE = re.compile(r"\b(?:\d{2,3}[- ][A-Z0-9]{2,6}[- ][A-Z0-9]{2,6}|[A-Z]{1,4}\d{2,6}[- ][A-Z0-9]{1,6})\b", re.I)
PART_FIELD_HINTS = ("part", "parts", "part_number", "part_numbers", "highlighted", "component", "components")


def _clean_part_token(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    # Strip common OCR/JSON punctuation but keep hyphenated part IDs.
    text = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" ", "-") if re.search(r"\d\s+[A-Z0-9]", text, re.I) else text
    # Keep broad context tokens, but drop clearly sentence-like values.
    if len(text) > 64 or text.count(" ") > 1:
        return None
    return text or None


def _extract_parts_recursive(value: Any, key_hint: str = "") -> list[str]:
    found: list[str] = []
    key_l = key_hint.lower()
    if isinstance(value, dict):
        for k, v in value.items():
            found.extend(_extract_parts_recursive(v, str(k)))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            found.extend(_extract_parts_recursive(item, key_hint))
    elif isinstance(value, str):
        # If the field name says this is a part field, preserve comma/newline separated values.
        if any(h in key_l for h in PART_FIELD_HINTS):
            for piece in re.split(r"[,;\n]+", value):
                cleaned = _clean_part_token(piece)
                if cleaned:
                    found.append(cleaned)
        # Also catch likely normalized part IDs in longer text.
        for match in PART_LIKE_RE.findall(value):
            cleaned = _clean_part_token(match)
            if cleaned:
                found.append(cleaned)
    else:
        if any(h in key_l for h in PART_FIELD_HINTS):
            cleaned = _clean_part_token(value)
            if cleaned:
                found.append(cleaned)
    out: list[str] = []
    seen = set()
    for item in found:
        # Avoid adding common labels that are useful topics but bad part graph nodes.
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.upper()
        if key not in seen:
            seen.add(key)
            out.append(normalized)
    return out


def extract_highlighted_parts(raw: dict[str, Any]) -> list[str]:
    direct_values: list[Any] = []
    for key in [
        "highlighted_parts", "highlighted_part_numbers", "part_numbers", "parts",
        "detected_parts", "important_parts", "page_parts", "catalog_parts",
        "catalog_supported_parts", "highlighted_part_ids", "key_parts", "mentioned_parts",
    ]:
        if key in raw and raw.get(key) not in (None, ""):
            direct_values.append(raw.get(key))
    found: list[str] = []
    for value in direct_values:
        found.extend(_extract_parts_recursive(value, "part_numbers"))
    if not found:
        # Some context exports put parts under nested objects such as entities.parts or highlights.parts.
        for key in ["entities", "highlights", "metadata", "payload", "extracted", "structured", "signals"]:
            if key in raw:
                found.extend(_extract_parts_recursive(raw.get(key), key))
    # Last-resort regex on summary/context only; this catches a few obvious part mentions without exploding topics.
    if not found:
        for key in ["summary", "page_summary", "context", "description"]:
            if key in raw:
                found.extend(_extract_parts_recursive(raw.get(key), "summary_part_mentions"))
    out: list[str] = []
    seen = set()
    for item in found:
        cleaned = _clean_part_token(item)
        if not cleaned:
            continue
        k = cleaned.upper()
        if k not in seen:
            seen.add(k)
            out.append(cleaned)
    return out


def first_present(record: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        if key in record and record.get(key) not in (None, ""):
            return record.get(key)
    return default


def normalize_context_record(raw: dict[str, Any], fallback_page_id: str | None = None) -> dict[str, Any]:
    page_id = first_present(raw, ["page_id", "page", "id", "page_key"], fallback_page_id or "")
    page_id = canonical_page_id(str(page_id))
    context_id = first_present(raw, ["context_id"], f"page_context:{page_id}")
    summary = first_present(raw, ["summary", "page_summary", "context", "text", "description"], "")
    role = first_present(raw, ["role", "page_role", "classification"], "unknown")
    confidence = first_present(raw, ["confidence", "confidence_label"], "unknown")
    score = first_present(raw, ["score", "confidence_score", "usable_confidence"], None)
    try:
        score_val = float(score) if score is not None and str(score) != "" else None
    except Exception:
        score_val = None
    topics = listify(first_present(raw, ["topics", "tags", "topic_labels"], []))
    highlighted_parts = extract_highlighted_parts(raw)
    warnings = listify(first_present(raw, ["warnings", "warning", "warning_categories"], []))
    errors = listify(first_present(raw, ["errors", "error", "error_categories"], []))
    model = first_present(raw, ["model", "context_model", "llm_model"], "unknown")
    prompt_version = first_present(raw, ["prompt_version", "version"], "unknown")
    return {
        "context_id": str(context_id),
        "page_id": page_id,
        "page_number": parse_page_number(page_id),
        "role": str(role or "unknown"),
        "summary": str(summary or ""),
        "topics": [str(x) for x in topics if str(x).strip()],
        "highlighted_parts": [str(x) for x in highlighted_parts if str(x).strip()],
        "confidence": str(confidence or "unknown"),
        "confidence_score": score_val,
        "context_model": str(model or "unknown"),
        "prompt_version": str(prompt_version or "unknown"),
        "warnings": [str(x) for x in warnings if str(x).strip()],
        "errors": [str(x) for x in errors if str(x).strip()],
        "canonical_source_truth": False,
        "can_answer_directly": False,
        "can_support_answer": True,
        "requires_citation": True,
        "rag_role": "retrieval_helper",
        "trust_scope": "page_context_summary",
        "payload": raw,
    }


def load_context_records(context_file: Path) -> list[dict[str, Any]]:
    data = json.loads(context_file.read_text(encoding="utf-8"))
    raw_records: list[tuple[dict[str, Any], str | None]] = []
    if isinstance(data, list):
        raw_records = [(x, None) for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        if isinstance(data.get("contexts"), list):
            raw_records = [(x, None) for x in data["contexts"] if isinstance(x, dict)]
        elif isinstance(data.get("records"), list):
            raw_records = [(x, None) for x in data["records"] if isinstance(x, dict)]
        elif isinstance(data.get("pages"), list):
            raw_records = [(x, None) for x in data["pages"] if isinstance(x, dict)]
        else:
            # Most page_contexts.json exports are mapping-like: page_id -> context payload.
            for key, value in data.items():
                if isinstance(value, dict):
                    raw_records.append((value, key))
    records = [normalize_context_record(raw, fallback) for raw, fallback in raw_records]
    # Deduplicate by context_id, last one wins.
    by_id = {rec["context_id"]: rec for rec in records}
    return list(by_id.values())


def connect(database_url: str):
    try:
        import psycopg
        return psycopg.connect(database_url)
    except ImportError:
        import psycopg2
        return psycopg2.connect(database_url)


def _execute(cur, sql: str, params: tuple[Any, ...] = ()) -> None:
    cur.execute(sql, params)


def _one(cur, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        _execute(cur, """
            create table if not exists page_context_records(
                context_id text primary key,
                page_id text not null,
                page_id_resolved text,
                page_number integer,
                role text,
                summary text,
                topics jsonb,
                highlighted_parts jsonb,
                confidence text,
                confidence_score double precision,
                context_model text,
                prompt_version text,
                trust_scope text,
                rag_role text,
                can_answer_directly boolean not null default false,
                can_support_answer boolean not null default true,
                requires_citation boolean not null default true,
                canonical_source_truth boolean not null default false,
                payload jsonb,
                updated_at timestamptz not null default now()
            )
        """)
        _execute(cur, """
            create table if not exists page_context_topics(
                context_id text not null,
                page_id text not null,
                topic text not null,
                payload jsonb,
                updated_at timestamptz not null default now(),
                primary key(context_id, topic)
            )
        """)
        _execute(cur, """
            create table if not exists page_context_highlighted_parts(
                context_id text not null,
                page_id text not null,
                part_number text not null,
                payload jsonb,
                updated_at timestamptz not null default now(),
                primary key(context_id, part_number)
            )
        """)
    conn.commit()


def resolve_page_id(cur, page_id: str) -> str | None:
    aliases = page_aliases(page_id)
    if not aliases:
        return None
    cur.execute("select page_id from pages where page_id = any(%s) limit 1", (aliases,))
    row = cur.fetchone()
    if row:
        return row[0]
    num = parse_page_number(page_id)
    if num is not None:
        try:
            cur.execute("select page_id from pages where page_number=%s limit 1", (num,))
            row = cur.fetchone()
            if row:
                return row[0]
        except Exception:
            pass
    return None


def graph_node_id(kind: str, value: str) -> str:
    if kind == "page_context":
        return f"page_context:{value}"
    if kind == "page":
        return f"page:{value}"
    if kind == "topic":
        return f"topic:{slugify(value)}"
    if kind == "part":
        return f"part:{slugify(value)}"
    return f"{kind}:{slugify(value)}"


def edge_id(edge_type: str, source: str, target: str) -> str:
    raw = f"{edge_type}:{source}->{target}"
    if len(raw) <= 240:
        return raw
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return f"{edge_type}:{digest}"


def _upsert_graph_node(cur, node_id: str, node_type: str, label: str, payload: dict[str, Any]) -> None:
    cur.execute(
        """
        insert into graph_nodes(node_id, node_type, label, payload, updated_at)
        values (%s,%s,%s,%s::jsonb,now())
        on conflict(node_id) do update set
            node_type=excluded.node_type,
            label=excluded.label,
            payload=excluded.payload,
            updated_at=now()
        """,
        (node_id, node_type, label, json.dumps(payload, default=_json_default)),
    )


def _upsert_graph_edge(cur, eid: str, source_id: str, target_id: str, edge_type_: str, payload: dict[str, Any]) -> None:
    cur.execute(
        """
        insert into graph_edges(edge_id, source_id, target_id, edge_type, payload, updated_at)
        values (%s,%s,%s,%s,%s::jsonb,now())
        on conflict(edge_id) do update set
            source_id=excluded.source_id,
            target_id=excluded.target_id,
            edge_type=excluded.edge_type,
            payload=excluded.payload,
            updated_at=now()
        """,
        (eid, source_id, target_id, edge_type_, json.dumps(payload, default=_json_default)),
    )


@dataclass
class LoadResult:
    summary: dict[str, Any]
    records: list[dict[str, Any]]
    graph_nodes: list[dict[str, Any]]
    graph_edges: list[dict[str, Any]]


def load_page_context_overlay(
    database_url: str,
    context_file: Path = DEFAULT_CONTEXT_FILE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    dry_run: bool = False,
) -> LoadResult:
    records = load_context_records(context_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_node_records: list[dict[str, Any]] = []
    graph_edge_records: list[dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    missing_page_resolutions = 0
    topic_edges = 0
    highlighted_part_edges = 0

    if not dry_run:
        conn = connect(database_url)
        ensure_schema(conn)
        with conn:
            with conn.cursor() as cur:
                for rec in records:
                    resolved = resolve_page_id(cur, rec["page_id"])
                    if not resolved:
                        missing_page_resolutions += 1
                        resolved = rec["page_id"]
                    context_id = graph_node_id("page_context", rec["page_id"])
                    rec["context_id"] = context_id
                    rec["page_id_resolved"] = resolved
                    cur.execute(
                        """
                        insert into page_context_records(
                            context_id, page_id, page_id_resolved, page_number, role, summary, topics,
                            highlighted_parts, confidence, confidence_score, context_model, prompt_version,
                            trust_scope, rag_role, can_answer_directly, can_support_answer, requires_citation,
                            canonical_source_truth, payload, updated_at
                        ) values (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
                        on conflict(context_id) do update set
                            page_id=excluded.page_id,
                            page_id_resolved=excluded.page_id_resolved,
                            page_number=excluded.page_number,
                            role=excluded.role,
                            summary=excluded.summary,
                            topics=excluded.topics,
                            highlighted_parts=excluded.highlighted_parts,
                            confidence=excluded.confidence,
                            confidence_score=excluded.confidence_score,
                            context_model=excluded.context_model,
                            prompt_version=excluded.prompt_version,
                            trust_scope=excluded.trust_scope,
                            rag_role=excluded.rag_role,
                            can_answer_directly=excluded.can_answer_directly,
                            can_support_answer=excluded.can_support_answer,
                            requires_citation=excluded.requires_citation,
                            canonical_source_truth=excluded.canonical_source_truth,
                            payload=excluded.payload,
                            updated_at=now()
                        """,
                        (
                            context_id,
                            rec["page_id"],
                            resolved,
                            rec["page_number"],
                            rec["role"],
                            rec["summary"],
                            json.dumps(rec["topics"], default=_json_default),
                            json.dumps(rec["highlighted_parts"], default=_json_default),
                            rec["confidence"],
                            rec["confidence_score"],
                            rec["context_model"],
                            rec["prompt_version"],
                            rec["trust_scope"],
                            rec["rag_role"],
                            rec["can_answer_directly"],
                            rec["can_support_answer"],
                            rec["requires_citation"],
                            rec["canonical_source_truth"],
                            json.dumps(rec["payload"], default=_json_default),
                        ),
                    )
                    page_node = graph_node_id("page", canonical_page_id(rec["page_id"]))
                    context_payload = {k: rec[k] for k in ["page_id", "role", "summary", "confidence", "topics", "highlighted_parts", "trust_scope", "rag_role", "can_answer_directly", "can_support_answer", "canonical_source_truth"]}
                    _upsert_graph_node(cur, context_id, "page_context", rec["summary"][:120] or context_id, context_payload)
                    graph_node_records.append({"node_id": context_id, "node_type": "page_context", "label": rec["summary"][:120], "payload": context_payload})
                    for etype, source, target in [("HAS_CONTEXT", page_node, context_id), ("SUMMARIZES", context_id, page_node)]:
                        eid = edge_id(etype, source, target)
                        payload = {"page_id": rec["page_id"], "page_id_resolved": resolved, "context_id": context_id, "created_by": VERSION}
                        _upsert_graph_edge(cur, eid, source, target, etype, payload)
                        graph_edge_records.append({"edge_id": eid, "source_id": source, "target_id": target, "edge_type": etype, "payload": payload})
                    for topic in rec["topics"]:
                        topic_id = graph_node_id("topic", topic)
                        _upsert_graph_node(cur, topic_id, "topic", topic, {"topic": topic, "created_by": VERSION})
                        graph_node_records.append({"node_id": topic_id, "node_type": "topic", "label": topic, "payload": {"topic": topic}})
                        eid = edge_id("TAGGED_AS", context_id, topic_id)
                        payload = {"page_id": rec["page_id"], "context_id": context_id, "topic": topic, "created_by": VERSION}
                        _upsert_graph_edge(cur, eid, context_id, topic_id, "TAGGED_AS", payload)
                        graph_edge_records.append({"edge_id": eid, "source_id": context_id, "target_id": topic_id, "edge_type": "TAGGED_AS", "payload": payload})
                        cur.execute(
                            """
                            insert into page_context_topics(context_id, page_id, topic, payload, updated_at)
                            values (%s,%s,%s,%s::jsonb,now())
                            on conflict(context_id, topic) do update set payload=excluded.payload, updated_at=now()
                            """,
                            (context_id, rec["page_id"], topic, json.dumps(payload, default=_json_default)),
                        )
                        topic_edges += 1
                    for part in rec["highlighted_parts"]:
                        part_id = graph_node_id("part", part)
                        _upsert_graph_node(cur, part_id, "part", part, {"part_number": part, "created_by": VERSION})
                        graph_node_records.append({"node_id": part_id, "node_type": "part", "label": part, "payload": {"part_number": part}})
                        eid = edge_id("HIGHLIGHTS_PART", context_id, part_id)
                        payload = {"page_id": rec["page_id"], "context_id": context_id, "part_number": part, "created_by": VERSION}
                        _upsert_graph_edge(cur, eid, context_id, part_id, "HIGHLIGHTS_PART", payload)
                        graph_edge_records.append({"edge_id": eid, "source_id": context_id, "target_id": part_id, "edge_type": "HIGHLIGHTS_PART", "payload": payload})
                        cur.execute(
                            """
                            insert into page_context_highlighted_parts(context_id, page_id, part_number, payload, updated_at)
                            values (%s,%s,%s,%s::jsonb,now())
                            on conflict(context_id, part_number) do update set payload=excluded.payload, updated_at=now()
                            """,
                            (context_id, rec["page_id"], part, json.dumps(payload, default=_json_default)),
                        )
                        highlighted_part_edges += 1
        conn.close()
    else:
        for rec in records:
            context_id = graph_node_id("page_context", rec["page_id"])
            rec["context_id"] = context_id
            graph_node_records.append({"node_id": context_id, "node_type": "page_context", "label": rec["summary"][:120], "payload": rec})
            topic_edges += len(rec["topics"])
            highlighted_part_edges += len(rec["highlighted_parts"])

    # Query final counts when possible.
    final_counts: dict[str, Any] = {}
    if not dry_run:
        conn = connect(database_url)
        with conn.cursor() as cur:
            for name, sql in {
                "postgres_page_context_records": "select count(*) from page_context_records",
                "postgres_page_context_graph_nodes": "select count(*) from graph_nodes where node_type='page_context'",
                "postgres_has_context_edges": "select count(*) from graph_edges where edge_type='HAS_CONTEXT'",
                "postgres_tagged_as_edges": "select count(*) from graph_edges where edge_type='TAGGED_AS' and source_id like 'page_context:%'",
                "postgres_highlights_part_edges": "select count(*) from graph_edges where edge_type='HIGHLIGHTS_PART' and source_id like 'page_context:%'",
                "postgres_context_direct_answer_records": "select count(*) from page_context_records where can_answer_directly",
                "postgres_context_canonical_source_truth_records": "select count(*) from page_context_records where canonical_source_truth",
                "postgres_context_missing_source_page_records": "select count(*) from page_context_records where page_id_resolved is null or page_id_resolved=''",
            }.items():
                try:
                    final_counts[name] = int(_one(cur, sql) or 0)
                except Exception:
                    final_counts[name] = None
        conn.close()

    summary = {
        "status": "OK",
        "version": VERSION,
        "context_file": str(context_file),
        "dry_run": dry_run,
        "context_records_input": len(records),
        "context_records_loaded": len(records),
        "pages_with_context_input": len({r["page_id"] for r in records}),
        "missing_page_resolutions": missing_page_resolutions,
        "context_graph_nodes_upserted": len([n for n in graph_node_records if n.get("node_type") == "page_context"]),
        "has_context_edges_upserted": len([e for e in graph_edge_records if e.get("edge_type") == "HAS_CONTEXT"]),
        "tagged_as_edges_upserted": topic_edges,
        "highlights_part_edges_upserted": highlighted_part_edges,
        "direct_answer_context_records": len([r for r in records if r.get("can_answer_directly")]),
        "canonical_source_truth_context_records": len([r for r in records if r.get("canonical_source_truth")]),
        "source_truth_mutation_records": 0,
        "created_at": now_iso,
        **final_counts,
    }
    write_json(output_dir / "trace_net_page_context_overlay_summary.json", summary)
    write_jsonl(output_dir / "trace_net_page_context_overlay_records.jsonl", records)
    write_json(output_dir / "trace_net_page_context_overlay_graph_nodes.json", graph_node_records)
    write_json(output_dir / "trace_net_page_context_overlay_graph_edges.json", graph_edge_records)
    write_report(output_dir / "trace_net_page_context_overlay_report.html", summary, records[:50])
    return LoadResult(summary, records, graph_node_records, graph_edge_records)


def write_report(path: Path, summary: dict[str, Any], sample_records: list[dict[str, Any]]) -> None:
    def esc(x: Any) -> str:
        import html
        return html.escape(str(x if x is not None else ""))
    rows = []
    for rec in sample_records:
        rows.append(
            "<tr>"
            f"<td>{esc(rec.get('page_id'))}</td>"
            f"<td>{esc(rec.get('role'))}</td>"
            f"<td>{esc(rec.get('confidence'))}</td>"
            f"<td>{esc(', '.join(rec.get('topics') or [])[:180])}</td>"
            f"<td>{esc((rec.get('summary') or '')[:240])}</td>"
            "</tr>"
        )
    html = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>TRACE-Net Page Context Overlay</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;}}table{{border-collapse:collapse;width:100%;}}td,th{{border:1px solid #ddd;padding:6px;vertical-align:top;}}th{{background:#f2f2f2;}}</style>
</head><body>
<h1>TRACE-Net Postgres Page Context Overlay</h1>
<p>Status: <b>{esc(summary.get('status'))}</b> Version: <code>{esc(summary.get('version'))}</code></p>
<h2>Summary</h2><pre>{esc(json.dumps(summary, indent=2, default=_json_default))}</pre>
<h2>Sample contexts</h2>
<table><thead><tr><th>Page</th><th>Role</th><th>Confidence</th><th>Topics</th><th>Summary</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Load TRACE-Net page context overlay into PostgreSQL and graph tables.")
    p.add_argument("--database-url", default="", help="PostgreSQL database URL. Defaults to TRACE_NET_DATABASE_URL env var if omitted.")
    p.add_argument("--context-file", default=str(DEFAULT_CONTEXT_FILE))
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--open", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    import os
    args = build_arg_parser().parse_args(argv)
    database_url = args.database_url or os.environ.get("TRACE_NET_DATABASE_URL", "")
    if not database_url and not args.dry_run:
        print("ERROR: --database-url or TRACE_NET_DATABASE_URL is required unless --dry-run is used")
        return 2
    context_file = Path(args.context_file)
    if not context_file.exists():
        print(f"ERROR: context file not found: {context_file}")
        return 2
    result = load_page_context_overlay(database_url, context_file=context_file, output_dir=Path(args.output_dir), dry_run=args.dry_run)
    s = result.summary
    print("TRACE-Net Postgres page context overlay")
    print(f"  Status: {s.get('status')}")
    print(f"  Version: {s.get('version')}")
    print(f"  Context file: {s.get('context_file')}")
    print(f"  Output dir: {args.output_dir}")
    print("  Summary:")
    for key in [
        "context_records_loaded", "pages_with_context_input", "postgres_page_context_records",
        "postgres_page_context_graph_nodes", "postgres_has_context_edges", "postgres_tagged_as_edges",
        "postgres_highlights_part_edges", "missing_page_resolutions", "direct_answer_context_records",
        "canonical_source_truth_context_records", "source_truth_mutation_records",
    ]:
        if key in s:
            print(f"    {key}: {s.get(key)}")
    print("Files written:")
    print(f"  summary: {Path(args.output_dir) / 'trace_net_page_context_overlay_summary.json'}")
    print(f"  records: {Path(args.output_dir) / 'trace_net_page_context_overlay_records.jsonl'}")
    print(f"  report_html: {Path(args.output_dir) / 'trace_net_page_context_overlay_report.html'}")
    if args.open:
        webbrowser.open((Path(args.output_dir) / "trace_net_page_context_overlay_report.html").resolve().as_uri())
    return 0 if s.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
