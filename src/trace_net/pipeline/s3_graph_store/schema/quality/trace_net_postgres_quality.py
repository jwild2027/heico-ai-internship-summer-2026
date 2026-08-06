"""Quality gate for TRACE-Net PostgreSQL loader v1."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_postgres_loader import VERSION, connect, _write_json

DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/postgres")
QUALITY_FILE = "trace_net_postgres_quality.json"


def _database_url_from_args(value: str | None) -> str:
    url = value or os.environ.get("TRACE_NET_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Database URL required. Pass --database-url or set TRACE_NET_DATABASE_URL.")
    return url


def _one(cur, sql: str, params: tuple[Any, ...] = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def collect_postgres_quality(database_url: str) -> dict[str, Any]:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            summary = {
                "postgres_pages": _one(cur, "select count(*) from pages"),
                "postgres_ocr_records": _one(cur, "select count(*) from ocr_records"),
                "postgres_ocr_text_records": _one(cur, "select count(*) from ocr_records where coalesce(length(text),0) > 0"),
                "postgres_graph_nodes": _one(cur, "select count(*) from graph_nodes"),
                "postgres_graph_edges": _one(cur, "select count(*) from graph_edges"),
                "postgres_evidence_consensus_records": _one(cur, "select count(*) from evidence_consensus_records"),
                "postgres_stage5_records": _one(cur, "select count(*) from stage5_decision_records"),
                "postgres_rag_eligibility_records": _one(cur, "select count(*) from rag_eligibility_records"),
                "postgres_rag_candidate_records": _one(cur, "select count(*) from rag_candidate_chunks"),
                "postgres_rag_candidate_safe_records": _one(cur, "select count(*) from rag_candidate_chunks where safe_for_rag = true"),
                "postgres_unsafe_rag_candidate_records": _one(cur, "select count(*) from rag_candidate_chunks where safe_for_rag = false"),
                "postgres_rag_candidate_missing_source_url": _one(cur, "select count(*) from rag_candidate_chunks where coalesce(source_url,'') = ''"),
                "postgres_citation_records": _one(cur, "select count(*) from source_citations"),
                "postgres_citation_missing_source_url": _one(cur, "select count(*) from source_citations where coalesce(source_url,'') = ''"),
                "postgres_feedback_events": _one(cur, "select count(*) from feedback_events"),
                "postgres_feedback_policy_signals": _one(cur, "select count(*) from feedback_policy_signals"),
                "postgres_quality_runs": _one(cur, "select count(*) from quality_runs"),
                "postgres_load_runs": _one(cur, "select count(*) from trace_net_load_runs"),
            }
    return summary


def run_quality(database_url: str, *, output_dir: Path, thresholds: Mapping[str, Any]) -> dict[str, Any]:
    summary = collect_postgres_quality(database_url)
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("pages", summary["postgres_pages"] >= int(thresholds.get("min_pages", 0)), f"pages={summary['postgres_pages']}; minimum={thresholds.get('min_pages', 0)}")
    check("ocr_records", summary["postgres_ocr_records"] >= int(thresholds.get("min_ocr_records", 0)), f"ocr_records={summary['postgres_ocr_records']}; minimum={thresholds.get('min_ocr_records', 0)}")
    check("rag_candidates", summary["postgres_rag_candidate_records"] >= int(thresholds.get("min_rag_candidates", 0)), f"rag_candidates={summary['postgres_rag_candidate_records']}; minimum={thresholds.get('min_rag_candidates', 0)}")
    check("citations", summary["postgres_citation_records"] >= int(thresholds.get("min_citations", 0)), f"citations={summary['postgres_citation_records']}; minimum={thresholds.get('min_citations', 0)}")
    check("unsafe_rag_candidates", summary["postgres_unsafe_rag_candidate_records"] <= int(thresholds.get("max_unsafe_rag_candidates", 0)), f"unsafe={summary['postgres_unsafe_rag_candidate_records']}; max={thresholds.get('max_unsafe_rag_candidates', 0)}")
    check("missing_candidate_source_url", summary["postgres_rag_candidate_missing_source_url"] <= int(thresholds.get("max_missing_candidate_source_url", 10**9)), f"missing_candidate_source_url={summary['postgres_rag_candidate_missing_source_url']}; max={thresholds.get('max_missing_candidate_source_url', 'None')}")
    check("missing_citation_source_url", summary["postgres_citation_missing_source_url"] <= int(thresholds.get("max_missing_citation_source_url", 10**9)), f"missing_citation_source_url={summary['postgres_citation_missing_source_url']}; max={thresholds.get('max_missing_citation_source_url', 'None')}")
    check("load_runs", summary["postgres_load_runs"] >= 1, f"load_runs={summary['postgres_load_runs']}; minimum=1")

    status = "OK" if all(c["ok"] for c in checks) else "FAIL"
    report = {
        "status": status,
        "version": VERSION,
        **summary,
        "checks": checks,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / QUALITY_FILE, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net PostgreSQL load quality")
    parser.add_argument("--database-url")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-pages", type=int, default=0)
    parser.add_argument("--min-ocr-records", type=int, default=0)
    parser.add_argument("--min-rag-candidates", type=int, default=0)
    parser.add_argument("--min-citations", type=int, default=0)
    parser.add_argument("--max-unsafe-rag-candidates", type=int, default=0)
    parser.add_argument("--max-missing-candidate-source-url", type=int)
    parser.add_argument("--max-missing-citation-source-url", type=int)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    thresholds = {
        "min_pages": args.min_pages,
        "min_ocr_records": args.min_ocr_records,
        "min_rag_candidates": args.min_rag_candidates,
        "min_citations": args.min_citations,
        "max_unsafe_rag_candidates": args.max_unsafe_rag_candidates,
    }
    if args.max_missing_candidate_source_url is not None:
        thresholds["max_missing_candidate_source_url"] = args.max_missing_candidate_source_url
    if args.max_missing_citation_source_url is not None:
        thresholds["max_missing_citation_source_url"] = args.max_missing_citation_source_url
    report = run_quality(_database_url_from_args(args.database_url), output_dir=Path(args.output_dir), thresholds=thresholds)
    print("TRACE-Net PostgreSQL quality gate")
    print(f"  Status: {report.get('status')}")
    print("  Summary:")
    for key in sorted(k for k in report if k.startswith("postgres_")):
        print(f"    {key}: {report[key]}")
    print("  Checks:")
    for check in report.get("checks", []):
        prefix = "OK" if check.get("ok") else "FAIL"
        print(f"    {prefix} {check.get('name')}: {check.get('detail')}")
    print(f"\nJSON: {Path(args.output_dir) / QUALITY_FILE}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
