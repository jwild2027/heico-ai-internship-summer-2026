from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

DEFAULT_SUMMARY = Path("local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2_summary.json")
DEFAULT_QUALITY = Path("local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2_quality.json")
VERSION = "trace_net_page_context_v2_quality_v1"


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def db_connect(database_url: str):
    try:
        import psycopg
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required. Install with: pip install 'psycopg[binary]'") from exc
    return psycopg.connect(database_url)


def collect_db_counts(database_url: str) -> Dict[str, Any]:
    counts: Dict[str, Any] = {}
    if not database_url:
        return counts
    with db_connect(database_url) as conn:
        with conn.cursor() as cur:
            def one(sql: str) -> int:
                try:
                    cur.execute(sql)
                    return int(cur.fetchone()[0] or 0)
                except Exception:
                    conn.rollback()
                    return 0
            counts["db_context_v2_records"] = one("select count(*) from page_context_v2_records")
            counts["db_pages_with_context_v2"] = one("select count(distinct page_id) from page_context_v2_records")
            counts["db_records_with_retrieval_cues"] = one("select count(*) from page_context_v2_records where jsonb_array_length(coalesce(retrieval_cues,'[]'::jsonb)) > 0")
            counts["db_records_with_answerable_questions"] = one("select count(*) from page_context_v2_records where jsonb_array_length(coalesce(answerable_questions,'[]'::jsonb)) > 0")
            counts["db_direct_answer_context_records"] = one("select count(*) from page_context_v2_records where coalesce((authority->>'can_answer_directly')::boolean,false) = true")
            counts["db_canonical_source_truth_context_records"] = one("select count(*) from page_context_v2_records where coalesce((authority->>'canonical_source_truth')::boolean,false) = true")
            counts["db_source_truth_mutation_records"] = one("select count(*) from page_context_v2_records where coalesce((authority->>'source_truth_mutation_allowed')::boolean,false) = true")
            counts["db_context_v2_graph_nodes"] = one("select count(*) from graph_nodes where node_type='page_context_v2'")
            counts["db_has_context_v2_edges"] = one("select count(*) from graph_edges where edge_type='HAS_CONTEXT_V2'")
    return counts


def build_quality(summary: Dict[str, Any], thresholds: Dict[str, Any]) -> Dict[str, Any]:
    checks = []

    def val(key: str, *fallbacks: str, default: int = 0) -> Any:
        for k in (key,) + fallbacks:
            if k in summary and summary.get(k) is not None:
                return summary.get(k)
        return default

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    status = summary.get("status")
    add("status_ok", status == "OK", f"status={status}")

    records = int(val("db_context_v2_records", "postgres_page_context_v2_records", "context_v2_records_generated"))
    pages = int(val("db_pages_with_context_v2", "postgres_pages_with_context_v2", "context_v2_records_generated"))
    cues = int(val("db_records_with_retrieval_cues", "postgres_context_v2_with_retrieval_cues", "records_with_retrieval_cues"))
    questions = int(val("db_records_with_answerable_questions", "postgres_context_v2_with_answerable_questions", "records_with_answerable_questions"))
    direct = int(val("db_direct_answer_context_records", "postgres_direct_answer_context_v2_records", "direct_answer_context_records"))
    canonical = int(val("db_canonical_source_truth_context_records", "postgres_canonical_source_truth_context_v2_records", "canonical_source_truth_context_records"))
    mutations = int(val("db_source_truth_mutation_records", "source_truth_mutation_records"))
    graph_nodes = int(val("db_context_v2_graph_nodes", "postgres_context_v2_graph_nodes"))
    graph_edges = int(val("db_has_context_v2_edges", "postgres_has_context_v2_edges"))

    add("context_v2_records", records >= thresholds["min_context_v2_records"], f"records={records}; minimum={thresholds['min_context_v2_records']}")
    add("pages_with_context_v2", pages >= thresholds["min_pages_with_context_v2"], f"pages={pages}; minimum={thresholds['min_pages_with_context_v2']}")
    add("records_with_retrieval_cues", cues >= thresholds["min_records_with_retrieval_cues"], f"cues={cues}; minimum={thresholds['min_records_with_retrieval_cues']}")
    add("records_with_answerable_questions", questions >= thresholds["min_records_with_answerable_questions"], f"questions={questions}; minimum={thresholds['min_records_with_answerable_questions']}")
    add("direct_answer_context_records", direct <= thresholds["max_direct_answer_context_records"], f"direct={direct}; max={thresholds['max_direct_answer_context_records']}")
    add("canonical_source_truth_context_records", canonical <= thresholds["max_canonical_source_truth_context_records"], f"canonical={canonical}; max={thresholds['max_canonical_source_truth_context_records']}")
    add("source_truth_mutations", mutations <= thresholds["max_source_truth_mutations"], f"mutations={mutations}; max={thresholds['max_source_truth_mutations']}")
    add("context_v2_graph_nodes", graph_nodes >= thresholds["min_context_v2_graph_nodes"], f"graph_nodes={graph_nodes}; minimum={thresholds['min_context_v2_graph_nodes']}")
    add("has_context_v2_edges", graph_edges >= thresholds["min_has_context_v2_edges"], f"graph_edges={graph_edges}; minimum={thresholds['min_has_context_v2_edges']}")

    ok = all(c["ok"] for c in checks)
    report_summary = {
        "status": "OK" if ok else "FAIL",
        "version": VERSION,
        "context_v2_records": records,
        "pages_with_context_v2": pages,
        "records_with_retrieval_cues": cues,
        "records_with_answerable_questions": questions,
        "direct_answer_context_records": direct,
        "canonical_source_truth_context_records": canonical,
        "source_truth_mutation_records": mutations,
        "context_v2_graph_nodes": graph_nodes,
        "has_context_v2_edges": graph_edges,
    }
    return {"status": report_summary["status"], "version": VERSION, "summary": report_summary, "checks": checks}


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Quality gate for TRACE-Net Page Context v2.")
    p.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    p.add_argument("--quality", default=str(DEFAULT_QUALITY))
    p.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL"))
    p.add_argument("--min-context-v2-records", type=int, default=1)
    p.add_argument("--min-pages-with-context-v2", type=int, default=1)
    p.add_argument("--min-records-with-retrieval-cues", type=int, default=1)
    p.add_argument("--min-records-with-answerable-questions", type=int, default=1)
    p.add_argument("--min-context-v2-graph-nodes", type=int, default=0)
    p.add_argument("--min-has-context-v2-edges", type=int, default=0)
    p.add_argument("--max-direct-answer-context-records", type=int, default=0)
    p.add_argument("--max-canonical-source-truth-context-records", type=int, default=0)
    p.add_argument("--max-source-truth-mutations", type=int, default=0)
    p.add_argument("--write-json", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = load_json(Path(args.summary))
    if args.database_url:
        summary.update(collect_db_counts(args.database_url))
    thresholds = {
        "min_context_v2_records": args.min_context_v2_records,
        "min_pages_with_context_v2": args.min_pages_with_context_v2,
        "min_records_with_retrieval_cues": args.min_records_with_retrieval_cues,
        "min_records_with_answerable_questions": args.min_records_with_answerable_questions,
        "min_context_v2_graph_nodes": args.min_context_v2_graph_nodes,
        "min_has_context_v2_edges": args.min_has_context_v2_edges,
        "max_direct_answer_context_records": args.max_direct_answer_context_records,
        "max_canonical_source_truth_context_records": args.max_canonical_source_truth_context_records,
        "max_source_truth_mutations": args.max_source_truth_mutations,
    }
    report = build_quality(summary, thresholds)
    print("TRACE-Net Page Context v2 quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for k, v in report["summary"].items():
        if k in {"status", "version"}:
            continue
        print(f"    {k}: {v}")
    print("  Checks:")
    for c in report["checks"]:
        print(f"    {'OK' if c['ok'] else 'FAIL'} {c['name']}: {c['detail']}")
    if args.write_json:
        Path(args.quality).parent.mkdir(parents=True, exist_ok=True)
        Path(args.quality).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nJSON: {args.quality}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
