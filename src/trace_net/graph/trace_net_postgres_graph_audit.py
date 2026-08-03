"""TRACE-Net PostgreSQL graph traversal audit v1.

Read-only audit that checks whether the Postgres graph/evidence load is internally
connected and usable before algorithm-filter/ranking changes are applied.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

VERSION = "trace_net_postgres_graph_traversal_audit_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/graph_audit")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
            n += 1
    return n


def database_url_from_args(value: str | None) -> str:
    url = value or os.environ.get("TRACE_NET_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Database URL required. Pass --database-url or set TRACE_NET_DATABASE_URL.")
    return url


def connect(database_url: str):
    try:
        import psycopg  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit("psycopg is required. Install with: pip install 'psycopg[binary]'") from exc
    return psycopg.connect(database_url)


def _one(cur, sql: str, params: tuple[Any, ...] = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _counter_rows(cur, sql: str) -> dict[str, int]:
    cur.execute(sql)
    out: dict[str, int] = {}
    for key, value in cur.fetchall():
        out[str(key or "")] = int(value or 0)
    return out


def _page_match_exists_sql(value_expr: str, page_alias: str = "p") -> str:
    """Return SQL predicate that matches canonical TRACE-Net page ids to OCR zip page rows.

    The local OCR export uses ids like zip_page_000003 while TRACE-Net evidence
    records use ids like t_p_120_1176_p000003.  Page_number is the stable bridge.
    """
    return f"""
        (
          {page_alias}.page_id = {value_expr}
          or {page_alias}.page_id = replace({value_expr}, 't_p_120_1176_p', 'zip_page_')
          or (
            {page_alias}.page_number is not null
            and {page_alias}.page_number = coalesce(
              nullif(substring({value_expr} from 'p0*([0-9]+)$'), '')::integer,
              nullif(substring({value_expr} from 'zip_page_0*([0-9]+)$'), '')::integer
            )
          )
          or {page_alias}.payload->>'page_id' = {value_expr}
          or {page_alias}.payload->>'source_page_id' = {value_expr}
        )
    """



class UnionFind:
    def __init__(self, items: Iterable[str]):
        self.parent = {x: x for x in items}
        self.size = {x: 1 for x in items}

    def find(self, x: str) -> str:
        parent = self.parent
        if x not in parent:
            parent[x] = x
            self.size[x] = 1
            return x
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]

    def component_sizes(self) -> list[int]:
        counts: Counter[str] = Counter(self.find(x) for x in self.parent)
        return sorted(counts.values(), reverse=True)


def compute_graph_components(node_ids: Sequence[str], edges: Sequence[tuple[str, str]]) -> dict[str, Any]:
    uf = UnionFind(node_ids)
    node_set = set(node_ids)
    orphan_edges = 0
    self_loops = 0
    for src, dst in edges:
        if src == dst:
            self_loops += 1
        if src not in node_set or dst not in node_set:
            orphan_edges += 1
            continue
        uf.union(src, dst)
    sizes = uf.component_sizes()
    singleton_count = sum(1 for s in sizes if s == 1)
    return {
        "component_count": len(sizes),
        "largest_component_nodes": sizes[0] if sizes else 0,
        "singleton_components": singleton_count,
        "orphan_edges_scan": orphan_edges,
        "self_loop_edges_scan": self_loops,
        "top_component_sizes": sizes[:10],
    }


def collect_graph_audit(database_url: str, *, max_samples: int = 20) -> dict[str, Any]:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            summary: dict[str, Any] = {
                "status": "OK",
                "version": VERSION,
                "created_at": _utc_now(),
                "postgres_pages": _one(cur, "select count(*) from pages"),
                "postgres_ocr_records": _one(cur, "select count(*) from ocr_records"),
                "postgres_ocr_text_records": _one(cur, "select count(*) from ocr_records where coalesce(length(text),0) > 0"),
                "postgres_graph_nodes": _one(cur, "select count(*) from graph_nodes"),
                "postgres_graph_edges": _one(cur, "select count(*) from graph_edges"),
                "postgres_rag_candidates": _one(cur, "select count(*) from rag_candidate_chunks"),
                "postgres_citations": _one(cur, "select count(*) from source_citations"),
                "postgres_evidence_consensus_records": _one(cur, "select count(*) from evidence_consensus_records"),
                "postgres_stage5_records": _one(cur, "select count(*) from stage5_decision_records"),
                "postgres_rag_eligibility_records": _one(cur, "select count(*) from rag_eligibility_records"),
                "postgres_feedback_events": _one(cur, "select count(*) from feedback_events"),
                "node_type_counts": _counter_rows(cur, "select coalesce(node_type,'') as k, count(*) from graph_nodes group by k order by count(*) desc, k"),
                "edge_type_counts": _counter_rows(cur, "select coalesce(edge_type,'') as k, count(*) from graph_edges group by k order by count(*) desc, k"),
                "ocr_classification_counts": _counter_rows(cur, "select coalesce(classification,'') as k, count(*) from ocr_records group by k order by count(*) desc, k"),
                "rag_bucket_counts": _counter_rows(cur, "select coalesce(rag_bucket,'') as k, count(*) from rag_candidate_chunks group by k order by k"),
            }

            # SQL link checks.
            summary.update({
                "graph_orphan_edges_sql": _one(cur, """
                    select count(*) from graph_edges e
                    left join graph_nodes s on s.node_id = e.source_id
                    left join graph_nodes t on t.node_id = e.target_id
                    where s.node_id is null or t.node_id is null
                """),
                "graph_self_loop_edges_sql": _one(cur, "select count(*) from graph_edges where source_id = target_id"),
                "pages_missing_source_url": _one(cur, "select count(*) from pages where coalesce(source_url,'') = ''"),
                "pages_missing_tiff_path": _one(cur, "select count(*) from pages where coalesce(tiff_path,'') = ''"),
                "pages_missing_ocr_path": _one(cur, "select count(*) from pages where coalesce(ocr_path,'') = ''"),
                "ocr_records_without_page": _one(cur, f"select count(*) from ocr_records o where not exists (select 1 from pages p where {_page_match_exists_sql('o.page_id')})"),
                "rag_candidates_without_page": _one(cur, f"select count(*) from rag_candidate_chunks r where not exists (select 1 from pages p where {_page_match_exists_sql('r.page_id')})"),
                "citations_without_page": _one(cur, f"select count(*) from source_citations c where not exists (select 1 from pages p where {_page_match_exists_sql('c.page_id')})"),
                "citations_without_candidate": _one(cur, "select count(*) from source_citations c left join rag_candidate_chunks r on r.candidate_id = c.candidate_id where coalesce(c.candidate_id,'') <> '' and r.candidate_id is null"),
                "evidence_without_page": _one(cur, f"select count(*) from evidence_consensus_records e where coalesce(e.page_id,'') <> '' and not exists (select 1 from pages p where {_page_match_exists_sql('e.page_id')})"),
                "stage5_without_page": _one(cur, f"select count(*) from stage5_decision_records s where coalesce(s.page_id,'') <> '' and not exists (select 1 from pages p where {_page_match_exists_sql('s.page_id')})"),
                "rag_eligibility_without_page": _one(cur, f"select count(*) from rag_eligibility_records r where coalesce(r.page_id,'') <> '' and not exists (select 1 from pages p where {_page_match_exists_sql('r.page_id')})"),
                "unsafe_rag_candidate_records": _one(cur, "select count(*) from rag_candidate_chunks where safe_for_rag = false"),
                "rag_candidate_missing_source_url": _one(cur, "select count(*) from rag_candidate_chunks where coalesce(source_url,'') = ''"),
                "citation_missing_source_url": _one(cur, "select count(*) from source_citations where coalesce(source_url,'') = ''"),
                "rag_candidate_missing_text": _one(cur, "select count(*) from rag_candidate_chunks where coalesce(text,'') = ''"),
                "rag_candidate_missing_confidence": _one(cur, "select count(*) from rag_candidate_chunks where usable_confidence is null"),
                "rag_candidate_missing_trust_tier": _one(cur, "select count(*) from rag_candidate_chunks where coalesce(trust_tier,'') = ''"),
            })

            # Page-to-graph coverage. Accept direct node ID, page: prefix, or payload page_id.
            summary.update({
                "pages_with_graph_node": _one(cur, """
                    select count(*) from pages p where exists (
                      select 1 from graph_nodes n
                      where n.node_id = p.page_id
                         or n.node_id = 'page:' || p.page_id
                         or position(p.page_id in n.node_id) > 0
                         or coalesce(n.label,'') = p.page_id
                         or position(p.page_id in coalesce(n.label,'')) > 0
                         or n.payload->>'page_id' = p.page_id
                         or n.payload->>'id' = p.page_id
                         or n.payload->>'page' = p.page_id
                         or position(p.page_id in n.payload::text) > 0
                         or (p.page_number is not null and position('p' || lpad(p.page_number::text, 6, '0') in n.node_id) > 0)
                         or (p.page_number is not null and position('p' || lpad(p.page_number::text, 6, '0') in coalesce(n.label,'')) > 0)
                         or (p.page_number is not null and position('p' || lpad(p.page_number::text, 6, '0') in n.payload::text) > 0)
                    )
                """),
                "pages_without_graph_node": _one(cur, """
                    select count(*) from pages p where not exists (
                      select 1 from graph_nodes n
                      where n.node_id = p.page_id
                         or n.node_id = 'page:' || p.page_id
                         or position(p.page_id in n.node_id) > 0
                         or coalesce(n.label,'') = p.page_id
                         or position(p.page_id in coalesce(n.label,'')) > 0
                         or n.payload->>'page_id' = p.page_id
                         or n.payload->>'id' = p.page_id
                         or n.payload->>'page' = p.page_id
                         or position(p.page_id in n.payload::text) > 0
                         or (p.page_number is not null and position('p' || lpad(p.page_number::text, 6, '0') in n.node_id) > 0)
                         or (p.page_number is not null and position('p' || lpad(p.page_number::text, 6, '0') in coalesce(n.label,'')) > 0)
                         or (p.page_number is not null and position('p' || lpad(p.page_number::text, 6, '0') in n.payload::text) > 0)
                    )
                """),
            })

            # Samples.
            cur.execute("""
                select e.edge_id, e.source_id, e.target_id, e.edge_type
                from graph_edges e
                left join graph_nodes s on s.node_id = e.source_id
                left join graph_nodes t on t.node_id = e.target_id
                where s.node_id is null or t.node_id is null
                limit %s
            """, (max_samples,))
            orphan_edge_samples = [
                {"edge_id": r[0], "source_id": r[1], "target_id": r[2], "edge_type": r[3]}
                for r in cur.fetchall()
            ]

            cur.execute("""
                select p.page_id from pages p where not exists (
                  select 1 from graph_nodes n
                  where n.node_id = p.page_id
                     or n.node_id = 'page:' || p.page_id
                     or position(p.page_id in n.node_id) > 0
                     or n.payload->>'page_id' = p.page_id
                     or (p.page_number is not null and position('p' || lpad(p.page_number::text, 6, '0') in n.node_id) > 0)
                     or (p.page_number is not null and position('p' || lpad(p.page_number::text, 6, '0') in n.payload::text) > 0)
                )
                order by p.page_id
                limit %s
            """, (max_samples,))
            missing_page_node_samples = [{"page_id": r[0]} for r in cur.fetchall()]

            cur.execute("select node_id from graph_nodes")
            node_ids = [str(r[0]) for r in cur.fetchall()]
            cur.execute("select source_id, target_id from graph_edges")
            edges = [(str(r[0] or ""), str(r[1] or "")) for r in cur.fetchall()]

    component_metrics = compute_graph_components(node_ids, edges)
    summary.update(component_metrics)
    summary["orphan_edge_samples"] = orphan_edge_samples
    summary["missing_page_node_samples"] = missing_page_node_samples

    warnings: list[str] = []
    if summary["graph_orphan_edges_sql"]:
        warnings.append("graph_orphan_edges_present")
    if summary["pages_without_graph_node"]:
        warnings.append("pages_without_graph_nodes_present")
    if summary["unsafe_rag_candidate_records"]:
        warnings.append("unsafe_rag_candidate_records_present")
    if summary["rag_candidate_missing_trust_tier"]:
        warnings.append("rag_candidate_trust_tier_column_incomplete")
    summary["warnings"] = warnings
    return summary


def build_graph_audit(database_url: str, *, output_dir: Path, max_samples: int = 20) -> dict[str, Any]:
    summary = collect_graph_audit(database_url, max_samples=max_samples)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "trace_net_graph_traversal_audit_summary.json", summary)
    _write_jsonl(output_dir / "trace_net_graph_traversal_orphan_edge_samples.jsonl", summary.get("orphan_edge_samples", []))
    _write_jsonl(output_dir / "trace_net_graph_traversal_missing_page_node_samples.jsonl", summary.get("missing_page_node_samples", []))

    nodes = [
        {"id": "graph_audit:run", "type": "graph_audit_run", "label": "TRACE-Net graph traversal audit", "status": summary["status"]},
        {"id": "graph_audit:postgres_graph", "type": "postgres_graph", "label": "Postgres graph"},
    ]
    edges = [{"source": "graph_audit:run", "target": "graph_audit:postgres_graph", "type": "AUDITED"}]
    for key in ("postgres_pages", "postgres_graph_nodes", "postgres_graph_edges", "component_count", "largest_component_nodes"):
        nid = f"graph_audit:metric:{key}"
        nodes.append({"id": nid, "type": "graph_audit_metric", "label": key, "value": summary.get(key)})
        edges.append({"source": "graph_audit:run", "target": nid, "type": "HAS_METRIC"})
    _write_json(output_dir / "trace_net_graph_traversal_audit_graph_nodes.json", nodes)
    _write_json(output_dir / "trace_net_graph_traversal_audit_graph_edges.json", edges)

    report = _render_markdown(summary)
    (output_dir / "trace_net_graph_traversal_audit_report.md").write_text(report, encoding="utf-8")
    (output_dir / "trace_net_graph_traversal_audit_report.html").write_text("<pre>" + report.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>", encoding="utf-8")
    return summary


def _render_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net Postgres Graph Traversal Audit v1",
        "",
        f"Status: **{summary.get('status')}**",
        f"Version: `{summary.get('version')}`",
        "",
        "## Core counts",
        f"- pages: {summary.get('postgres_pages')}",
        f"- OCR records: {summary.get('postgres_ocr_records')}",
        f"- graph nodes: {summary.get('postgres_graph_nodes')}",
        f"- graph edges: {summary.get('postgres_graph_edges')}",
        f"- RAG candidates: {summary.get('postgres_rag_candidates')}",
        f"- citations: {summary.get('postgres_citations')}",
        "",
        "## Traversal metrics",
        f"- components: {summary.get('component_count')}",
        f"- largest component nodes: {summary.get('largest_component_nodes')}",
        f"- singleton components: {summary.get('singleton_components')}",
        f"- orphan edges: {summary.get('graph_orphan_edges_sql')}",
        f"- self-loop edges: {summary.get('graph_self_loop_edges_sql')}",
        "",
        "## Page/source coverage",
        f"- pages with graph node: {summary.get('pages_with_graph_node')}",
        f"- pages without graph node: {summary.get('pages_without_graph_node')}",
        f"- pages missing source URL: {summary.get('pages_missing_source_url')}",
        f"- pages missing TIFF path: {summary.get('pages_missing_tiff_path')}",
        f"- pages missing OCR path: {summary.get('pages_missing_ocr_path')}",
        "",
        "## Safety/link checks",
        f"- unsafe RAG candidate records: {summary.get('unsafe_rag_candidate_records')}",
        f"- RAG candidates without page: {summary.get('rag_candidates_without_page')}",
        f"- citations without page: {summary.get('citations_without_page')}",
        f"- citations without candidate: {summary.get('citations_without_candidate')}",
        f"- RAG candidate missing source URL: {summary.get('rag_candidate_missing_source_url')}",
        f"- citation missing source URL: {summary.get('citation_missing_source_url')}",
        "",
        "## Warnings",
    ]
    warnings = summary.get("warnings") or []
    if warnings:
        lines.extend([f"- {w}" for w in warnings])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit TRACE-Net Postgres graph traversal and linkage quality.")
    parser.add_argument("--database-url")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-samples", type=int, default=20)
    parser.add_argument("--open", action="store_true", help="Print path to HTML report; GUI opening is not attempted.")
    args = parser.parse_args(argv)

    database_url = database_url_from_args(args.database_url)
    summary = build_graph_audit(database_url, output_dir=Path(args.output_dir), max_samples=args.max_samples)
    print("TRACE-Net Postgres graph traversal audit")
    print(f"  Status: {summary['status']}")
    print(f"  Output dir: {Path(args.output_dir)}")
    print("  Summary:")
    for key in [
        "postgres_pages", "postgres_ocr_records", "postgres_graph_nodes", "postgres_graph_edges",
        "component_count", "largest_component_nodes", "singleton_components", "graph_orphan_edges_sql",
        "pages_with_graph_node", "pages_without_graph_node", "unsafe_rag_candidate_records",
        "rag_candidate_missing_trust_tier",
    ]:
        print(f"    {key}: {summary.get(key)}")
    if args.open:
        print(f"  Review: {Path(args.output_dir) / 'trace_net_graph_traversal_audit_report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
