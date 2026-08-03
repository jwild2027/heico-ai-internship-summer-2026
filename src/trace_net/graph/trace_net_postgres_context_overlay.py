"""TRACE-Net PostgreSQL context overlay v1.

This is a lightweight operator/architecture context overlay for local TRACE-Net
pipeline testing. It imports a small JSON summary of the current architecture,
counts, policies, and route decisions into PostgreSQL.

Important rule: this overlay is not source evidence. It is project context for
operators, QA, and future admin retrieval. It must not be used as direct manual
answer evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

VERSION = "trace_net_postgres_context_overlay_v1"
DEFAULT_SEED_PATH = Path(
    "local_data/organization/trace_net/context_overlay/trace_net_context_seed.json"
)
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/context_overlay")

DDL = """
CREATE TABLE IF NOT EXISTS trace_net_context_overlay_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    overlay_version TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source_kind TEXT NOT NULL DEFAULT 'local_context_summary',
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    authority_scope TEXT NOT NULL DEFAULT 'project_context_only',
    answer_authority TEXT NOT NULL DEFAULT 'none',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trace_net_context_overlay_items (
    item_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES trace_net_context_overlay_snapshots(snapshot_id) ON DELETE CASCADE,
    item_type TEXT NOT NULL,
    item_key TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    source_ref TEXT,
    authority_scope TEXT NOT NULL DEFAULT 'project_context_only',
    answer_authority TEXT NOT NULL DEFAULT 'none',
    allowed_usage JSONB NOT NULL DEFAULT '["operator_context", "routing_context"]'::jsonb,
    blocked_usage JSONB NOT NULL DEFAULT '["manual_answer_evidence", "source_text_evidence", "verified_part_evidence"]'::jsonb,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, item_type, item_key)
);

CREATE TABLE IF NOT EXISTS trace_net_context_overlay_edges (
    edge_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES trace_net_context_overlay_snapshots(snapshot_id) ON DELETE CASCADE,
    source_item_id TEXT NOT NULL REFERENCES trace_net_context_overlay_items(item_id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,
    target_item_id TEXT NOT NULL REFERENCES trace_net_context_overlay_items(item_id) ON DELETE CASCADE,
    authority_scope TEXT NOT NULL DEFAULT 'project_context_only',
    answer_authority TEXT NOT NULL DEFAULT 'none',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, source_item_id, edge_type, target_item_id)
);

CREATE TABLE IF NOT EXISTS trace_net_context_overlay_metrics (
    metric_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES trace_net_context_overlay_snapshots(snapshot_id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL,
    metric_label TEXT NOT NULL,
    metric_value NUMERIC,
    metric_unit TEXT NOT NULL DEFAULT 'count',
    authority_scope TEXT NOT NULL DEFAULT 'project_context_only',
    answer_authority TEXT NOT NULL DEFAULT 'none',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, metric_key)
);

CREATE INDEX IF NOT EXISTS idx_trace_net_context_items_snapshot_type
    ON trace_net_context_overlay_items(snapshot_id, item_type);
CREATE INDEX IF NOT EXISTS idx_trace_net_context_items_payload_gin
    ON trace_net_context_overlay_items USING GIN(payload);
CREATE INDEX IF NOT EXISTS idx_trace_net_context_edges_snapshot_type
    ON trace_net_context_overlay_edges(snapshot_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_trace_net_context_metrics_snapshot_key
    ON trace_net_context_overlay_metrics(snapshot_id, metric_key);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_id(*parts: Any, prefix: str = "ctx") -> str:
    text = "|".join(str(p) for p in parts if p not in (None, ""))
    digest = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing context seed JSON: {path}")
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise ValueError(f"Context seed must be a JSON object: {path}")
    return data


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _jsonb(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, ensure_ascii=False)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_seed(seed: Mapping[str, Any]) -> dict[str, Any]:
    snapshot_id = str(
        seed.get("snapshot_id")
        or _stable_id(seed.get("title", "trace-net-context"), seed.get("overlay_version", VERSION), prefix="snapshot")
    )
    overlay_version = str(seed.get("overlay_version") or VERSION)
    title = str(seed.get("title") or "TRACE-Net context overlay")
    description = str(seed.get("description") or "")
    source_kind = str(seed.get("source_kind") or "local_context_summary")
    source_refs = _as_list(seed.get("source_refs"))
    payload = dict(seed.get("payload") or {}) if isinstance(seed.get("payload"), Mapping) else {}

    items: list[dict[str, Any]] = []
    for raw in _as_list(seed.get("items")):
        if not isinstance(raw, Mapping):
            continue
        item_type = str(raw.get("item_type") or "context")
        item_key = str(raw.get("item_key") or raw.get("key") or raw.get("title") or _stable_id(raw))
        item = {
            "item_id": str(raw.get("item_id") or _stable_id(snapshot_id, item_type, item_key, prefix="ctx_item")),
            "snapshot_id": snapshot_id,
            "item_type": item_type,
            "item_key": item_key,
            "title": str(raw.get("title") or item_key),
            "summary": str(raw.get("summary") or ""),
            "source_ref": raw.get("source_ref"),
            "authority_scope": str(raw.get("authority_scope") or "project_context_only"),
            "answer_authority": str(raw.get("answer_authority") or "none"),
            "allowed_usage": _as_list(raw.get("allowed_usage") or ["operator_context", "routing_context"]),
            "blocked_usage": _as_list(
                raw.get("blocked_usage")
                or ["manual_answer_evidence", "source_text_evidence", "verified_part_evidence"]
            ),
            "payload": dict(raw.get("payload") or {}) if isinstance(raw.get("payload"), Mapping) else {},
        }
        items.append(item)

    item_id_by_key = {item["item_key"]: item["item_id"] for item in items}
    edges: list[dict[str, Any]] = []
    missing_edges: list[dict[str, Any]] = []
    for raw in _as_list(seed.get("edges")):
        if not isinstance(raw, Mapping):
            continue
        source_key = str(raw.get("source_key") or raw.get("source_item_key") or "")
        target_key = str(raw.get("target_key") or raw.get("target_item_key") or "")
        edge_type = str(raw.get("edge_type") or "RELATED_TO")
        source_item_id = str(raw.get("source_item_id") or item_id_by_key.get(source_key) or "")
        target_item_id = str(raw.get("target_item_id") or item_id_by_key.get(target_key) or "")
        if not source_item_id or not target_item_id:
            missing_edges.append(dict(raw))
            continue
        edges.append(
            {
                "edge_id": str(
                    raw.get("edge_id")
                    or _stable_id(snapshot_id, source_item_id, edge_type, target_item_id, prefix="ctx_edge")
                ),
                "snapshot_id": snapshot_id,
                "source_item_id": source_item_id,
                "edge_type": edge_type,
                "target_item_id": target_item_id,
                "authority_scope": str(raw.get("authority_scope") or "project_context_only"),
                "answer_authority": str(raw.get("answer_authority") or "none"),
                "payload": dict(raw.get("payload") or {}) if isinstance(raw.get("payload"), Mapping) else {},
            }
        )

    metrics: list[dict[str, Any]] = []
    for raw in _as_list(seed.get("metrics")):
        if not isinstance(raw, Mapping):
            continue
        metric_key = str(raw.get("metric_key") or raw.get("key") or raw.get("metric_label") or "metric")
        metrics.append(
            {
                "metric_id": str(raw.get("metric_id") or _stable_id(snapshot_id, metric_key, prefix="ctx_metric")),
                "snapshot_id": snapshot_id,
                "metric_key": metric_key,
                "metric_label": str(raw.get("metric_label") or metric_key),
                "metric_value": raw.get("metric_value"),
                "metric_unit": str(raw.get("metric_unit") or "count"),
                "authority_scope": str(raw.get("authority_scope") or "project_context_only"),
                "answer_authority": str(raw.get("answer_authority") or "none"),
                "payload": dict(raw.get("payload") or {}) if isinstance(raw.get("payload"), Mapping) else {},
            }
        )

    return {
        "snapshot": {
            "snapshot_id": snapshot_id,
            "overlay_version": overlay_version,
            "title": title,
            "description": description,
            "source_kind": source_kind,
            "source_refs": source_refs,
            "authority_scope": str(seed.get("authority_scope") or "project_context_only"),
            "answer_authority": str(seed.get("answer_authority") or "none"),
            "payload": payload,
        },
        "items": items,
        "edges": edges,
        "metrics": metrics,
        "missing_edges": missing_edges,
    }


def _import_psycopg():
    try:
        import psycopg  # type: ignore

        return "psycopg3", psycopg
    except Exception:
        pass
    try:
        import psycopg2  # type: ignore

        return "psycopg2", psycopg2
    except Exception as exc:
        raise RuntimeError(
            "PostgreSQL context overlay requires psycopg or psycopg2. "
            "Install one of: pip install psycopg[binary] or pip install psycopg2-binary."
        ) from exc


def _connect(dsn: str):
    _, module = _import_psycopg()
    return module.connect(dsn)


def _run_ddl(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def _upsert_snapshot(conn: Any, snapshot: Mapping[str, Any]) -> None:
    sql = """
    INSERT INTO trace_net_context_overlay_snapshots (
        snapshot_id, overlay_version, title, description, source_kind, source_refs,
        authority_scope, answer_authority, payload, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, now())
    ON CONFLICT (snapshot_id) DO UPDATE SET
        overlay_version = EXCLUDED.overlay_version,
        title = EXCLUDED.title,
        description = EXCLUDED.description,
        source_kind = EXCLUDED.source_kind,
        source_refs = EXCLUDED.source_refs,
        authority_scope = EXCLUDED.authority_scope,
        answer_authority = EXCLUDED.answer_authority,
        payload = EXCLUDED.payload,
        updated_at = now();
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                snapshot["snapshot_id"],
                snapshot["overlay_version"],
                snapshot["title"],
                snapshot["description"],
                snapshot["source_kind"],
                _jsonb(snapshot["source_refs"]),
                snapshot["authority_scope"],
                snapshot["answer_authority"],
                _jsonb(snapshot["payload"]),
            ),
        )


def _upsert_items(conn: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    sql = """
    INSERT INTO trace_net_context_overlay_items (
        item_id, snapshot_id, item_type, item_key, title, summary, source_ref,
        authority_scope, answer_authority, allowed_usage, blocked_usage, payload, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, now())
    ON CONFLICT (snapshot_id, item_type, item_key) DO UPDATE SET
        title = EXCLUDED.title,
        summary = EXCLUDED.summary,
        source_ref = EXCLUDED.source_ref,
        authority_scope = EXCLUDED.authority_scope,
        answer_authority = EXCLUDED.answer_authority,
        allowed_usage = EXCLUDED.allowed_usage,
        blocked_usage = EXCLUDED.blocked_usage,
        payload = EXCLUDED.payload,
        updated_at = now();
    """
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                sql,
                (
                    row["item_id"],
                    row["snapshot_id"],
                    row["item_type"],
                    row["item_key"],
                    row["title"],
                    row["summary"],
                    row.get("source_ref"),
                    row["authority_scope"],
                    row["answer_authority"],
                    _jsonb(row["allowed_usage"]),
                    _jsonb(row["blocked_usage"]),
                    _jsonb(row["payload"]),
                ),
            )


def _upsert_edges(conn: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    sql = """
    INSERT INTO trace_net_context_overlay_edges (
        edge_id, snapshot_id, source_item_id, edge_type, target_item_id,
        authority_scope, answer_authority, payload, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
    ON CONFLICT (snapshot_id, source_item_id, edge_type, target_item_id) DO UPDATE SET
        authority_scope = EXCLUDED.authority_scope,
        answer_authority = EXCLUDED.answer_authority,
        payload = EXCLUDED.payload,
        updated_at = now();
    """
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                sql,
                (
                    row["edge_id"],
                    row["snapshot_id"],
                    row["source_item_id"],
                    row["edge_type"],
                    row["target_item_id"],
                    row["authority_scope"],
                    row["answer_authority"],
                    _jsonb(row["payload"]),
                ),
            )


def _upsert_metrics(conn: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    sql = """
    INSERT INTO trace_net_context_overlay_metrics (
        metric_id, snapshot_id, metric_key, metric_label, metric_value, metric_unit,
        authority_scope, answer_authority, payload, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
    ON CONFLICT (snapshot_id, metric_key) DO UPDATE SET
        metric_label = EXCLUDED.metric_label,
        metric_value = EXCLUDED.metric_value,
        metric_unit = EXCLUDED.metric_unit,
        authority_scope = EXCLUDED.authority_scope,
        answer_authority = EXCLUDED.answer_authority,
        payload = EXCLUDED.payload,
        updated_at = now();
    """
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                sql,
                (
                    row["metric_id"],
                    row["snapshot_id"],
                    row["metric_key"],
                    row["metric_label"],
                    row.get("metric_value"),
                    row["metric_unit"],
                    row["authority_scope"],
                    row["answer_authority"],
                    _jsonb(row["payload"]),
                ),
            )


def _delete_not_in(cur: Any, table: str, id_column: str, snapshot_id: str, ids: Sequence[str]) -> None:
    """Delete rows for one snapshot whose id is not in the provided id list."""
    if ids:
        placeholders = ", ".join(["%s"] * len(ids))
        sql = f"DELETE FROM {table} WHERE snapshot_id = %s AND {id_column} NOT IN ({placeholders});"
        cur.execute(sql, (snapshot_id, *ids))
    else:
        cur.execute(f"DELETE FROM {table} WHERE snapshot_id = %s;", (snapshot_id,))


def _delete_missing_for_snapshot(
    conn: Any,
    snapshot_id: str,
    items: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    metrics: Sequence[Mapping[str, Any]],
) -> None:
    """Keep the snapshot idempotent by pruning stale rows for this snapshot."""
    item_ids = [str(row["item_id"]) for row in items]
    edge_ids = [str(row["edge_id"]) for row in edges]
    metric_ids = [str(row["metric_id"]) for row in metrics]
    with conn.cursor() as cur:
        _delete_not_in(cur, "trace_net_context_overlay_edges", "edge_id", snapshot_id, edge_ids)
        _delete_not_in(cur, "trace_net_context_overlay_items", "item_id", snapshot_id, item_ids)
        _delete_not_in(cur, "trace_net_context_overlay_metrics", "metric_id", snapshot_id, metric_ids)

def load_context_overlay(conn: Any, normalized: Mapping[str, Any], prune: bool = True) -> dict[str, Any]:
    snapshot = normalized["snapshot"]
    items = list(normalized["items"])
    edges = list(normalized["edges"])
    metrics = list(normalized["metrics"])

    _run_ddl(conn)
    _upsert_snapshot(conn, snapshot)
    if prune:
        _delete_missing_for_snapshot(conn, snapshot["snapshot_id"], items, edges, metrics)
    _upsert_items(conn, items)
    _upsert_edges(conn, edges)
    _upsert_metrics(conn, metrics)
    conn.commit()

    return {
        "version": VERSION,
        "loaded_at": _utc_now(),
        "snapshot_id": snapshot["snapshot_id"],
        "items_loaded": len(items),
        "edges_loaded": len(edges),
        "metrics_loaded": len(metrics),
        "missing_edges_skipped": len(normalized.get("missing_edges", [])),
        "authority_scope": snapshot["authority_scope"],
        "answer_authority": snapshot["answer_authority"],
    }


def quality_report(conn: Any, snapshot_id: str | None = None) -> dict[str, Any]:
    where = ""
    params: tuple[Any, ...] = ()
    if snapshot_id:
        where = "WHERE snapshot_id = %s"
        params = (snapshot_id,)

    report: dict[str, Any] = {"version": VERSION, "checked_at": _utc_now(), "snapshot_id": snapshot_id}
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM trace_net_context_overlay_snapshots {where};", params)
        report["snapshots"] = int(cur.fetchone()[0])
        cur.execute(f"SELECT count(*) FROM trace_net_context_overlay_items {where};", params)
        report["items"] = int(cur.fetchone()[0])
        cur.execute(f"SELECT count(*) FROM trace_net_context_overlay_edges {where};", params)
        report["edges"] = int(cur.fetchone()[0])
        cur.execute(f"SELECT count(*) FROM trace_net_context_overlay_metrics {where};", params)
        report["metrics"] = int(cur.fetchone()[0])

        cur.execute(
            f"""
            SELECT count(*)
            FROM trace_net_context_overlay_items
            {where + (' AND ' if where else 'WHERE ')}
                  (authority_scope <> 'project_context_only' OR answer_authority <> 'none');
            """,
            params,
        )
        report["unsafe_item_authority_rows"] = int(cur.fetchone()[0])

        cur.execute(
            f"""
            SELECT count(*)
            FROM trace_net_context_overlay_edges
            {where + (' AND ' if where else 'WHERE ')}
                  (authority_scope <> 'project_context_only' OR answer_authority <> 'none');
            """,
            params,
        )
        report["unsafe_edge_authority_rows"] = int(cur.fetchone()[0])

        cur.execute(
            f"""
            SELECT count(*)
            FROM trace_net_context_overlay_metrics
            {where + (' AND ' if where else 'WHERE ')}
                  (authority_scope <> 'project_context_only' OR answer_authority <> 'none');
            """,
            params,
        )
        report["unsafe_metric_authority_rows"] = int(cur.fetchone()[0])

        orphan_params = params + params
        snapshot_clause_a = ""
        snapshot_clause_b = ""
        if snapshot_id:
            snapshot_clause_a = "AND e.snapshot_id = %s"
            snapshot_clause_b = "AND e.snapshot_id = %s"
        cur.execute(
            f"""
            SELECT count(*)
            FROM trace_net_context_overlay_edges e
            LEFT JOIN trace_net_context_overlay_items s ON s.item_id = e.source_item_id
            LEFT JOIN trace_net_context_overlay_items t ON t.item_id = e.target_item_id
            WHERE (s.item_id IS NULL OR t.item_id IS NULL)
            {snapshot_clause_a};
            """,
            params,
        )
        report["orphan_edges"] = int(cur.fetchone()[0])

        if snapshot_id:
            cur.execute(
                """
                SELECT item_type, count(*)
                FROM trace_net_context_overlay_items
                WHERE snapshot_id = %s
                GROUP BY item_type
                ORDER BY item_type;
                """,
                (snapshot_id,),
            )
        else:
            cur.execute(
                """
                SELECT item_type, count(*)
                FROM trace_net_context_overlay_items
                GROUP BY item_type
                ORDER BY item_type;
                """
            )
        report["item_type_counts"] = {str(k): int(v) for k, v in cur.fetchall()}

    report["ok"] = (
        report["snapshots"] >= 1
        and report["items"] > 0
        and report["metrics"] > 0
        and report["unsafe_item_authority_rows"] == 0
        and report["unsafe_edge_authority_rows"] == 0
        and report["unsafe_metric_authority_rows"] == 0
        and report["orphan_edges"] == 0
    )
    return report


def load_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load lightweight TRACE-Net context overlay into PostgreSQL.")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dsn", default=os.environ.get("TRACE_NET_PG_DSN") or os.environ.get("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true", help="Validate and write summary without connecting to PostgreSQL.")
    parser.add_argument("--init-only", action="store_true", help="Only create/update the schema, do not load seed rows.")
    parser.add_argument("--no-prune", action="store_true", help="Do not delete stale rows from the same snapshot.")
    args = parser.parse_args(argv)

    seed = _read_json(args.seed)
    normalized = _normalize_seed(seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "trace_net_context_overlay_schema.sql").write_text(DDL, encoding="utf-8")

    dry_summary = {
        "version": VERSION,
        "checked_at": _utc_now(),
        "seed": str(args.seed),
        "snapshot_id": normalized["snapshot"]["snapshot_id"],
        "items": len(normalized["items"]),
        "edges": len(normalized["edges"]),
        "metrics": len(normalized["metrics"]),
        "missing_edges_skipped": len(normalized.get("missing_edges", [])),
        "dry_run": bool(args.dry_run),
    }
    _write_json(args.output_dir / "trace_net_context_overlay_normalized_preview.json", normalized)

    if args.dry_run:
        _write_json(args.output_dir / "trace_net_context_overlay_load_summary.json", dry_summary)
        print(json.dumps(dry_summary, indent=2, sort_keys=True))
        return 0

    if not args.dsn:
        print("Missing PostgreSQL DSN. Set TRACE_NET_PG_DSN or pass --dsn.", file=sys.stderr)
        return 2

    conn = _connect(args.dsn)
    try:
        _run_ddl(conn)
        if args.init_only:
            summary = {**dry_summary, "init_only": True, "dry_run": False}
        else:
            summary = load_context_overlay(conn, normalized, prune=not args.no_prune)
        _write_json(args.output_dir / "trace_net_context_overlay_load_summary.json", summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    finally:
        conn.close()


def check_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net context overlay quality in PostgreSQL.")
    parser.add_argument("--snapshot-id", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dsn", default=os.environ.get("TRACE_NET_PG_DSN") or os.environ.get("DATABASE_URL"))
    args = parser.parse_args(argv)

    if not args.dsn:
        print("Missing PostgreSQL DSN. Set TRACE_NET_PG_DSN or pass --dsn.", file=sys.stderr)
        return 2

    conn = _connect(args.dsn)
    try:
        report = quality_report(conn, snapshot_id=args.snapshot_id)
    finally:
        conn.close()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "trace_net_context_overlay_quality_report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1
