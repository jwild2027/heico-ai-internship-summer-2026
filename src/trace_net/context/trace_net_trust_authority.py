"""TRACE-Net Trust Semantics / Trust Authority v1.

This module turns trust tiers into explicit authority semantics.  It is a
read/overlay step for the local PostgreSQL test backend: it does not mutate
source truth, RAG eligibility, production ranking, or feedback.  It creates a
record for each safe RAG candidate that says what the candidate's trust tier is
allowed to mean.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "trace_net_trust_authority_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/trust_authority")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(*parts: Any, prefix: str = "authority") -> str:
    text = "|".join(str(p or "") for p in parts)
    digest = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, default=json_default) + "\n")


def to_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "safe", "ok"}:
        return True
    if text in {"0", "false", "f", "no", "n", "unsafe"}:
        return False
    return default


def to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def connect(database_url: str):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required. Install with: pip install 'psycopg[binary]'") from exc
    return psycopg.connect(database_url, row_factory=dict_row)


def table_exists(cur, table: str) -> bool:
    cur.execute("select to_regclass(%s) is not null as exists", (f"public.{table}",))
    row = cur.fetchone() or {}
    return bool(row.get("exists"))


def table_columns(cur, table: str) -> set[str]:
    cur.execute(
        """
        select column_name from information_schema.columns
        where table_schema='public' and table_name=%s
        """,
        (table,),
    )
    return {str(r["column_name"]) for r in cur.fetchall()}


def ensure_schema(cur) -> None:
    cur.execute(
        """
        create table if not exists trust_authority_records(
          authority_id text primary key,
          candidate_id text,
          page_id text,
          rag_bucket text,
          evidence_layer text,
          trust_tier text,
          trust_scope text,
          evidence_authority text,
          claim_authority text,
          rag_role text,
          can_answer_directly boolean not null default false,
          can_support_answer boolean not null default true,
          requires_citation boolean not null default true,
          requires_source_trace boolean not null default true,
          source_truth_mutation_allowed boolean not null default false,
          canonical_source_truth boolean not null default false,
          safe_for_rag boolean not null default true,
          source_url text,
          tiff_path text,
          ocr_path text,
          usable_confidence double precision,
          payload jsonb not null default '{}'::jsonb,
          updated_at timestamptz not null default now()
        )
        """
    )
    cur.execute("create index if not exists idx_trust_authority_candidate on trust_authority_records(candidate_id)")
    cur.execute("create index if not exists idx_trust_authority_page on trust_authority_records(page_id)")
    cur.execute("create index if not exists idx_trust_authority_bucket on trust_authority_records(rag_bucket)")
    cur.execute("create index if not exists idx_trust_authority_scope on trust_authority_records(trust_scope)")


def derive_authority(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Map a RAG candidate row to trust-authority semantics.

    Trust tier answers "how trusted?".  This function answers "trusted for what?".
    """
    bucket = str(row.get("rag_bucket") or "").strip()
    layer = str(row.get("evidence_layer") or "").strip()
    tier = str(row.get("trust_tier") or "").strip().upper() or "C"
    safe_for_rag = to_bool(row.get("safe_for_rag"), default=True)

    # Defaults are conservative.
    authority: Dict[str, Any] = {
        "trust_scope": "unknown",
        "evidence_authority": "review_only",
        "claim_authority": "no_direct_claim_authority",
        "rag_role": "review_only",
        "can_answer_directly": False,
        "can_support_answer": False,
        "requires_citation": True,
        "requires_source_trace": True,
        "source_truth_mutation_allowed": False,
        "canonical_source_truth": False,
    }

    if bucket == "source_evidence" or layer == "source_trace":
        authority.update(
            {
                "trust_scope": "source_trace",
                "evidence_authority": "source_truth",
                "claim_authority": "source_exists_only",
                "rag_role": "source_citation_evidence",
                "can_answer_directly": False,
                "can_support_answer": True,
                "requires_citation": True,
                "requires_source_trace": True,
                "canonical_source_truth": True,
            }
        )
    elif bucket == "source_text_evidence" or layer in {"source_text", "source_text_evidence"}:
        authority.update(
            {
                "trust_scope": "source_text",
                "evidence_authority": "source_backed_ocr_text",
                "claim_authority": "ocr_text_claim_with_citation",
                "rag_role": "source_text_context",
                "can_answer_directly": True,
                "can_support_answer": True,
                "requires_citation": True,
                "requires_source_trace": True,
                "canonical_source_truth": False,
            }
        )
    elif bucket == "verified_part_evidence" or layer in {"part_catalog", "verified_part_evidence"}:
        authority.update(
            {
                "trust_scope": "part_catalog",
                "evidence_authority": "verified_part_reference",
                "claim_authority": "part_page_relationship",
                "rag_role": "verified_part_evidence",
                "can_answer_directly": True,
                "can_support_answer": True,
                "requires_citation": True,
                "requires_source_trace": True,
                "canonical_source_truth": False,
            }
        )
    elif bucket == "derived_context" or layer in {"table_tile_text_refined", "derived_context"}:
        authority.update(
            {
                "trust_scope": "table_tile_text_refined",
                "evidence_authority": "derived_context",
                "claim_authority": "supporting_context_only",
                "rag_role": "derived_context_only",
                "can_answer_directly": False,
                "can_support_answer": True,
                "requires_citation": True,
                "requires_source_trace": True,
                "canonical_source_truth": False,
            }
        )
    elif bucket in {"table_candidate", "table_tiles"} or layer in {"table_candidate", "table_tiles"}:
        authority.update(
            {
                "trust_scope": layer or bucket,
                "evidence_authority": "routing_or_preprocessing_artifact",
                "claim_authority": "no_direct_claim_authority",
                "rag_role": "routing_only",
                "can_answer_directly": False,
                "can_support_answer": False,
                "requires_citation": True,
                "requires_source_trace": True,
                "canonical_source_truth": False,
            }
        )

    # Unsafe/non-RAG rows should not be answer-capable even if a caller supplied a
    # misleading bucket.
    if not safe_for_rag or tier == "D":
        authority["can_answer_directly"] = False
        authority["can_support_answer"] = False
        authority["rag_role"] = "excluded_or_review_only"

    return authority


def load_candidate_rows(cur) -> List[Dict[str, Any]]:
    if not table_exists(cur, "rag_candidate_chunks"):
        return []
    cols = table_columns(cur, "rag_candidate_chunks")
    # Trust overlay should already populate trust_tier, but keep the SQL robust.
    select_cols = []
    for col in [
        "candidate_id",
        "page_id",
        "rag_bucket",
        "evidence_layer",
        "trust_tier",
        "usable_confidence",
        "source_url",
        "tiff_path",
        "ocr_path",
        "safe_for_rag",
        "payload",
    ]:
        if col in cols:
            select_cols.append(col)
        elif col == "payload":
            select_cols.append("'{}'::jsonb as payload")
        elif col == "safe_for_rag":
            select_cols.append("true as safe_for_rag")
        elif col == "usable_confidence":
            select_cols.append("NULL::double precision as usable_confidence")
        else:
            select_cols.append(f"NULL::text as {col}")
    cur.execute(f"select {', '.join(select_cols)} from rag_candidate_chunks order by candidate_id")
    return [dict(r) for r in cur.fetchall()]


def build_authority_records(candidate_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for row in candidate_rows:
        payload = row.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {"raw_payload": payload}
        if not isinstance(payload, dict):
            payload = {"payload": payload}
        auth = derive_authority(row)
        candidate_id = str(row.get("candidate_id") or "")
        page_id = str(row.get("page_id") or "")
        bucket = str(row.get("rag_bucket") or "")
        layer = str(row.get("evidence_layer") or "")
        tier = str(row.get("trust_tier") or "").strip().upper() or "C"
        authority_id = f"trust_authority:{stable_id(candidate_id, page_id, bucket, layer, tier, prefix='') }"
        records.append(
            {
                "authority_id": authority_id,
                "candidate_id": candidate_id,
                "page_id": page_id,
                "rag_bucket": bucket,
                "evidence_layer": layer,
                "trust_tier": tier,
                "usable_confidence": to_float(row.get("usable_confidence")),
                "source_url": str(row.get("source_url") or ""),
                "tiff_path": str(row.get("tiff_path") or ""),
                "ocr_path": str(row.get("ocr_path") or ""),
                "safe_for_rag": to_bool(row.get("safe_for_rag"), default=True),
                **auth,
                "payload": {"candidate_payload": payload, "authority_version": VERSION},
            }
        )
    return records


def insert_authority_records(cur, records: Sequence[Mapping[str, Any]]) -> None:
    cur.execute("delete from trust_authority_records")
    for rec in records:
        cur.execute(
            """
            insert into trust_authority_records(
              authority_id, candidate_id, page_id, rag_bucket, evidence_layer, trust_tier,
              trust_scope, evidence_authority, claim_authority, rag_role,
              can_answer_directly, can_support_answer, requires_citation, requires_source_trace,
              source_truth_mutation_allowed, canonical_source_truth, safe_for_rag,
              source_url, tiff_path, ocr_path, usable_confidence, payload, updated_at
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
            on conflict(authority_id) do update set
              candidate_id=excluded.candidate_id,
              page_id=excluded.page_id,
              rag_bucket=excluded.rag_bucket,
              evidence_layer=excluded.evidence_layer,
              trust_tier=excluded.trust_tier,
              trust_scope=excluded.trust_scope,
              evidence_authority=excluded.evidence_authority,
              claim_authority=excluded.claim_authority,
              rag_role=excluded.rag_role,
              can_answer_directly=excluded.can_answer_directly,
              can_support_answer=excluded.can_support_answer,
              requires_citation=excluded.requires_citation,
              requires_source_trace=excluded.requires_source_trace,
              source_truth_mutation_allowed=excluded.source_truth_mutation_allowed,
              canonical_source_truth=excluded.canonical_source_truth,
              safe_for_rag=excluded.safe_for_rag,
              source_url=excluded.source_url,
              tiff_path=excluded.tiff_path,
              ocr_path=excluded.ocr_path,
              usable_confidence=excluded.usable_confidence,
              payload=excluded.payload,
              updated_at=now()
            """,
            (
                rec["authority_id"],
                rec["candidate_id"],
                rec["page_id"],
                rec["rag_bucket"],
                rec["evidence_layer"],
                rec["trust_tier"],
                rec["trust_scope"],
                rec["evidence_authority"],
                rec["claim_authority"],
                rec["rag_role"],
                rec["can_answer_directly"],
                rec["can_support_answer"],
                rec["requires_citation"],
                rec["requires_source_trace"],
                rec["source_truth_mutation_allowed"],
                rec["canonical_source_truth"],
                rec["safe_for_rag"],
                rec["source_url"],
                rec["tiff_path"],
                rec["ocr_path"],
                rec["usable_confidence"],
                json.dumps(rec.get("payload") or {}, ensure_ascii=False, default=json_default),
            ),
        )


def one(cur, sql: str, params: Sequence[Any] = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return None
    return next(iter(row.values()))


def collect_summary(cur, records: Sequence[Mapping[str, Any]], output_dir: Path) -> Dict[str, Any]:
    c_bucket = Counter(str(r.get("rag_bucket") or "") for r in records)
    c_scope = Counter(str(r.get("trust_scope") or "") for r in records)
    c_evidence = Counter(str(r.get("evidence_authority") or "") for r in records)
    c_claim = Counter(str(r.get("claim_authority") or "") for r in records)
    c_role = Counter(str(r.get("rag_role") or "") for r in records)
    c_tier = Counter(str(r.get("trust_tier") or "") for r in records)
    pages = int(one(cur, "select count(*) from pages") or 0) if table_exists(cur, "pages") else 0
    candidate_count = int(one(cur, "select count(*) from rag_candidate_chunks") or 0) if table_exists(cur, "rag_candidate_chunks") else 0
    authority_count = int(one(cur, "select count(*) from trust_authority_records") or 0)
    missing_authority = 0
    missing_trust_tier = 0
    if table_exists(cur, "rag_candidate_chunks"):
        missing_authority = int(
            one(
                cur,
                """
                select count(*) from rag_candidate_chunks c
                where not exists (select 1 from trust_authority_records a where a.candidate_id = c.candidate_id)
                """,
            )
            or 0
        )
        missing_trust_tier = int(one(cur, "select count(*) from rag_candidate_chunks where trust_tier is null or btrim(trust_tier)='' ") or 0)
    summary = {
        "status": "OK",
        "version": VERSION,
        "created_at": utc_now_iso(),
        "output_dir": str(output_dir),
        "pages": pages,
        "rag_candidate_records": candidate_count,
        "trust_authority_records": authority_count,
        "missing_authority_records": missing_authority,
        "missing_candidate_trust_tier": missing_trust_tier,
        "source_evidence_authority_records": c_bucket.get("source_evidence", 0),
        "source_text_authority_records": c_bucket.get("source_text_evidence", 0),
        "verified_part_authority_records": c_bucket.get("verified_part_evidence", 0),
        "derived_context_authority_records": c_bucket.get("derived_context", 0),
        "source_evidence_direct_answer_records": sum(1 for r in records if r.get("rag_bucket") == "source_evidence" and r.get("can_answer_directly")),
        "derived_context_direct_answer_records": sum(1 for r in records if r.get("rag_bucket") == "derived_context" and r.get("can_answer_directly")),
        "derived_context_canonical_source_truth_records": sum(1 for r in records if r.get("rag_bucket") == "derived_context" and r.get("canonical_source_truth")),
        "unsafe_authority_records": sum(1 for r in records if (not r.get("safe_for_rag")) and (r.get("can_answer_directly") or r.get("can_support_answer"))),
        "missing_source_url_authority_records": sum(1 for r in records if r.get("safe_for_rag") and not r.get("source_url")),
        "source_truth_mutation_records": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "requires_citation_records": sum(1 for r in records if r.get("requires_citation")),
        "requires_source_trace_records": sum(1 for r in records if r.get("requires_source_trace")),
        "can_answer_directly_records": sum(1 for r in records if r.get("can_answer_directly")),
        "can_support_answer_records": sum(1 for r in records if r.get("can_support_answer")),
        "trust_scope_counts": dict(sorted(c_scope.items())),
        "evidence_authority_counts": dict(sorted(c_evidence.items())),
        "claim_authority_counts": dict(sorted(c_claim.items())),
        "rag_role_counts": dict(sorted(c_role.items())),
        "rag_bucket_counts": dict(sorted(c_bucket.items())),
        "trust_tier_counts": dict(sorted(c_tier.items())),
        "production_ranking_changed": False,
    }
    return summary


def build_graph_artifacts(records: Sequence[Mapping[str, Any]], max_records: int = 5000) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    for rec in records[:max_records]:
        cand = f"candidate:{rec.get('candidate_id')}"
        page = f"page:{rec.get('page_id')}"
        scope = f"trust_scope:{rec.get('trust_scope')}"
        authority = f"evidence_authority:{rec.get('evidence_authority')}"
        role = f"rag_role:{rec.get('rag_role')}"
        nodes.setdefault(cand, {"id": cand, "type": "candidate", "label": rec.get("candidate_id")})
        nodes.setdefault(page, {"id": page, "type": "page", "label": rec.get("page_id")})
        nodes.setdefault(scope, {"id": scope, "type": "trust_scope", "label": rec.get("trust_scope")})
        nodes.setdefault(authority, {"id": authority, "type": "evidence_authority", "label": rec.get("evidence_authority")})
        nodes.setdefault(role, {"id": role, "type": "rag_role", "label": rec.get("rag_role")})
        edges.append({"source": cand, "target": page, "type": "AUTHORITY_FOR_PAGE"})
        edges.append({"source": cand, "target": scope, "type": "HAS_TRUST_SCOPE"})
        edges.append({"source": cand, "target": authority, "type": "HAS_EVIDENCE_AUTHORITY"})
        edges.append({"source": cand, "target": role, "type": "HAS_RAG_ROLE"})
    return list(nodes.values()), edges


def write_report(summary: Mapping[str, Any], output_dir: Path) -> None:
    rows = []
    for key in [
        "pages",
        "rag_candidate_records",
        "trust_authority_records",
        "missing_authority_records",
        "missing_candidate_trust_tier",
        "source_evidence_authority_records",
        "source_text_authority_records",
        "verified_part_authority_records",
        "derived_context_authority_records",
        "source_evidence_direct_answer_records",
        "derived_context_direct_answer_records",
        "derived_context_canonical_source_truth_records",
        "unsafe_authority_records",
        "source_truth_mutation_records",
    ]:
        rows.append(f"<tr><th>{html.escape(key)}</th><td>{html.escape(str(summary.get(key)))}</td></tr>")
    doc = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>TRACE-Net Trust Authority</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}} table{{border-collapse:collapse}} th,td{{border:1px solid #ccc;padding:6px 10px;text-align:left}} pre{{background:#f5f5f5;padding:12px}}</style></head>
<body>
<h1>TRACE-Net Trust Semantics / Trust Authority v1</h1>
<p>Status: <b>{html.escape(str(summary.get('status')))}</b> &nbsp; Version: <code>{html.escape(str(summary.get('version')))}</code></p>
<p>This report explains what each trust tier is allowed to mean. It is an overlay: it does not mutate source truth, RAG eligibility, feedback, or production ranking.</p>
<table>{''.join(rows)}</table>
<h2>Trust scopes</h2><pre>{html.escape(json.dumps(summary.get('trust_scope_counts', {}), indent=2))}</pre>
<h2>Evidence authority</h2><pre>{html.escape(json.dumps(summary.get('evidence_authority_counts', {}), indent=2))}</pre>
<h2>Claim authority</h2><pre>{html.escape(json.dumps(summary.get('claim_authority_counts', {}), indent=2))}</pre>
<h2>RAG roles</h2><pre>{html.escape(json.dumps(summary.get('rag_role_counts', {}), indent=2))}</pre>
</body></html>"""
    (output_dir / "trace_net_trust_authority_report.html").write_text(doc, encoding="utf-8")
    md = [
        "# TRACE-Net Trust Semantics / Trust Authority v1",
        "",
        f"Status: **{summary.get('status')}**",
        f"Version: `{summary.get('version')}`",
        "",
        "This overlay keeps `trust_tier`, but adds what the trust tier is allowed to mean.",
        "",
        "## Summary",
    ]
    for key in ["trust_authority_records", "source_evidence_authority_records", "source_text_authority_records", "verified_part_authority_records", "derived_context_authority_records", "unsafe_authority_records", "source_truth_mutation_records"]:
        md.append(f"- **{key}**: {summary.get(key)}")
    (output_dir / "trace_net_trust_authority_report.md").write_text("\n".join(md), encoding="utf-8")


def build_trust_authority(database_url: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            rows = load_candidate_rows(cur)
            records = build_authority_records(rows)
            insert_authority_records(cur, records)
            conn.commit()
            summary = collect_summary(cur, records, output_dir)
    nodes, edges = build_graph_artifacts(records)
    write_json(output_dir / "trace_net_trust_authority_summary.json", summary)
    write_jsonl(output_dir / "trace_net_trust_authority_records.jsonl", records)
    write_json(output_dir / "trace_net_trust_authority_graph_nodes.json", nodes)
    write_json(output_dir / "trace_net_trust_authority_graph_edges.json", edges)
    write_report(summary, output_dir)
    return summary


def maybe_open(path: Path) -> None:
    if not path.exists():
        return
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        os.system(f"open {json.dumps(str(path))}")
    else:
        os.system(f"xdg-open {json.dumps(str(path))} >/dev/null 2>&1 &")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net trust semantics / trust authority overlay")
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL", ""))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)
    if not args.database_url:
        print("ERROR: --database-url or TRACE_NET_DATABASE_URL is required", file=sys.stderr)
        return 2
    summary = build_trust_authority(args.database_url, Path(args.output_dir))
    print("TRACE-Net trust semantics / trust authority")
    print(f"  Status: {summary.get('status')}")
    print(f"  Version: {summary.get('version')}")
    print(f"  Output dir: {args.output_dir}")
    print("  Summary:")
    for key in [
        "pages",
        "rag_candidate_records",
        "trust_authority_records",
        "missing_authority_records",
        "source_evidence_authority_records",
        "source_text_authority_records",
        "verified_part_authority_records",
        "derived_context_authority_records",
        "derived_context_direct_answer_records",
        "derived_context_canonical_source_truth_records",
        "unsafe_authority_records",
        "source_truth_mutation_records",
    ]:
        print(f"    {key}: {summary.get(key)}")
    out = Path(args.output_dir)
    print("Files written:")
    for label, rel in [
        ("summary", "trace_net_trust_authority_summary.json"),
        ("records", "trace_net_trust_authority_records.jsonl"),
        ("report_html", "trace_net_trust_authority_report.html"),
        ("graph_nodes", "trace_net_trust_authority_graph_nodes.json"),
        ("graph_edges", "trace_net_trust_authority_graph_edges.json"),
    ]:
        print(f"  {label}: {out / rel}")
    if args.open:
        maybe_open(out / "trace_net_trust_authority_report.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
