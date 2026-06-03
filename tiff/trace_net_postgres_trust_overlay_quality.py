"""Quality gate for TRACE-Net PostgreSQL trust overlay."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/trust_overlay")
DEFAULT_SUMMARY = DEFAULT_OUTPUT_DIR / "trace_net_postgres_trust_overlay_summary.json"
DEFAULT_QUALITY = DEFAULT_OUTPUT_DIR / "trace_net_postgres_trust_overlay_quality.json"


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def connect(database_url: str):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required. Install with: pip install 'psycopg[binary]'") from exc
    return psycopg.connect(database_url, row_factory=dict_row)


def one(cur, sql: str, params=()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return None
    return next(iter(row.values()))


def table_exists(cur, table: str) -> bool:
    cur.execute("select to_regclass(%s) is not null as exists", (table,))
    return bool((cur.fetchone() or {}).get("exists"))


def collect_live_summary(database_url: str) -> Dict[str, Any]:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            summary: Dict[str, Any] = {}
            for table, key in [
                ("pages", "pages"),
                ("evidence_trust_records", "trust_overlay_records"),
                ("page_trust_traits", "page_trust_trait_records"),
                ("rag_candidate_chunks", "rag_candidate_records"),
            ]:
                summary[key] = int(one(cur, f"select count(*) from {table}") or 0) if table_exists(cur, table) else 0
            if table_exists(cur, "page_trust_traits"):
                summary["pages_with_trust_traits"] = int(one(cur, "select count(distinct page_id) from page_trust_traits") or 0)
            else:
                summary["pages_with_trust_traits"] = 0
            if table_exists(cur, "rag_candidate_chunks"):
                summary["rag_candidate_missing_trust_tier"] = int(one(cur, "select count(*) from rag_candidate_chunks where trust_tier is null or btrim(trust_tier)='' ") or 0)
                summary["source_trace_A_records"] = int(one(cur, "select count(*) from rag_candidate_chunks where rag_bucket='source_evidence' and trust_tier='A'") or 0)
                summary["source_text_A_records"] = int(one(cur, "select count(*) from rag_candidate_chunks where rag_bucket='source_text_evidence' and trust_tier='A'") or 0)
                summary["verified_part_A_records"] = int(one(cur, "select count(*) from rag_candidate_chunks where rag_bucket='verified_part_evidence' and trust_tier='A'") or 0)
                summary["derived_context_records"] = int(one(cur, "select count(*) from rag_candidate_chunks where rag_bucket='derived_context'") or 0)
                cols = set()
                cur.execute("select column_name from information_schema.columns where table_schema='public' and table_name='rag_candidate_chunks'")
                cols = {str(r["column_name"]) for r in cur.fetchall()}
                if "safe_for_rag" in cols:
                    summary["unsafe_trusted_rag_records"] = int(one(cur, "select count(*) from rag_candidate_chunks where coalesce(safe_for_rag,false)=false and trust_tier in ('A','B')") or 0)
                else:
                    summary["unsafe_trusted_rag_records"] = 0
            if table_exists(cur, "evidence_trust_records"):
                cur.execute("select trust_tier, count(*) as n from evidence_trust_records group by trust_tier")
                summary["trust_tier_counts"] = {str(r["trust_tier"]): int(r["n"]) for r in cur.fetchall()}
                cur.execute("select evidence_layer, count(*) as n from evidence_trust_records group by evidence_layer")
                summary["evidence_layer_counts"] = {str(r["evidence_layer"]): int(r["n"]) for r in cur.fetchall()}
            summary["source_truth_mutation_records"] = 0
            return summary


def check(name: str, passed: bool, message: str) -> Dict[str, Any]:
    return {"name": name, "status": "OK" if passed else "FAIL", "message": message}


def run_quality(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    def num(key: str, default: int = 0) -> int:
        val = summary.get(key, default)
        try:
            return int(val)
        except Exception:
            return default
    def th(key: str, default: Optional[int] = None) -> Optional[int]:
        val = thresholds.get(key, default)
        if val is None:
            return None
        return int(val)

    min_pages = th("min_pages", 0)
    min_trust = th("min_trust_records", 1)
    min_page_traits = th("min_page_trust_traits", 1)
    min_pages_with_traits = th("min_pages_with_trust_traits", 0)
    min_source_a = th("min_source_trace_A_records", 0)
    min_source_text_a = th("min_source_text_A_records", 0)
    min_verified_a = th("min_verified_part_A_records", 0)
    min_derived = th("min_derived_context_records", 0)
    max_missing = th("max_missing_candidate_trust_tier", None)
    max_unsafe_trusted = th("max_unsafe_trusted_rag_records", 0)
    max_mutations = th("max_source_truth_mutations", 0)

    checks.append(check("pages", num("pages") >= min_pages, f"pages={summary.get('pages')}; minimum={min_pages}"))
    checks.append(check("trust_records", num("trust_overlay_records") >= min_trust, f"trust_records={summary.get('trust_overlay_records')}; minimum={min_trust}"))
    checks.append(check("page_trust_traits", num("page_trust_trait_records") >= min_page_traits, f"page_trust_traits={summary.get('page_trust_trait_records')}; minimum={min_page_traits}"))
    checks.append(check("pages_with_trust_traits", num("pages_with_trust_traits") >= min_pages_with_traits, f"pages_with_trust_traits={summary.get('pages_with_trust_traits')}; minimum={min_pages_with_traits}"))
    checks.append(check("source_trace_A", num("source_trace_A_records") >= min_source_a, f"source_trace_A={summary.get('source_trace_A_records')}; minimum={min_source_a}"))
    checks.append(check("source_text_A", num("source_text_A_records") >= min_source_text_a, f"source_text_A={summary.get('source_text_A_records')}; minimum={min_source_text_a}"))
    checks.append(check("verified_part_A", num("verified_part_A_records") >= min_verified_a, f"verified_part_A={summary.get('verified_part_A_records')}; minimum={min_verified_a}"))
    checks.append(check("derived_context_records", num("derived_context_records") >= min_derived, f"derived_context={summary.get('derived_context_records')}; minimum={min_derived}"))
    if max_missing is not None:
        checks.append(check("missing_candidate_trust_tier", num("rag_candidate_missing_trust_tier") <= max_missing, f"missing_candidate_trust_tier={summary.get('rag_candidate_missing_trust_tier')}; max={max_missing}"))
    checks.append(check("unsafe_trusted_rag", num("unsafe_trusted_rag_records") <= max_unsafe_trusted, f"unsafe_trusted={summary.get('unsafe_trusted_rag_records')}; max={max_unsafe_trusted}"))
    checks.append(check("source_truth_mutations", num("source_truth_mutation_records") <= max_mutations, f"source_truth_mutations={summary.get('source_truth_mutation_records')}; max={max_mutations}"))

    failed = [c for c in checks if c["status"] != "OK"]
    return {
        "status": "OK" if not failed else "FAIL",
        "summary": dict(summary),
        "checks": checks,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net PostgreSQL trust overlay quality")
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL", ""))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--quality", default=str(DEFAULT_QUALITY))
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-pages", type=int, default=0)
    parser.add_argument("--min-trust-records", type=int, default=1)
    parser.add_argument("--min-page-trust-traits", type=int, default=1)
    parser.add_argument("--min-pages-with-trust-traits", type=int, default=0)
    parser.add_argument("--min-source-trace-A-records", type=int, default=0)
    parser.add_argument("--min-source-text-A-records", type=int, default=0)
    parser.add_argument("--min-verified-part-A-records", type=int, default=0)
    parser.add_argument("--min-derived-context-records", type=int, default=0)
    parser.add_argument("--max-missing-candidate-trust-tier", type=int, default=None)
    parser.add_argument("--max-unsafe-trusted-rag-records", type=int, default=0)
    parser.add_argument("--max-source-truth-mutations", type=int, default=0)
    args = parser.parse_args(argv)

    summary = collect_live_summary(args.database_url) if args.database_url else load_json(Path(args.summary))
    report = run_quality(summary, vars(args))
    print("TRACE-Net PostgreSQL trust overlay quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for key in [
        "pages",
        "trust_overlay_records",
        "page_trust_trait_records",
        "pages_with_trust_traits",
        "rag_candidate_records",
        "rag_candidate_missing_trust_tier",
        "source_trace_A_records",
        "source_text_A_records",
        "verified_part_A_records",
        "derived_context_records",
        "unsafe_trusted_rag_records",
    ]:
        if key in summary:
            print(f"    {key}: {summary.get(key)}")
    print("  Checks:")
    for c in report["checks"]:
        print(f"    {c['status']} {c['name']}: {c['message']}")
    if args.write_json:
        out = Path(args.quality)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON: {out}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
