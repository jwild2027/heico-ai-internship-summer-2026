"""Quality gate for TRACE-Net Trust Semantics / Trust Authority v1."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/trust_authority")
DEFAULT_SUMMARY = DEFAULT_OUTPUT_DIR / "trace_net_trust_authority_summary.json"
DEFAULT_QUALITY = DEFAULT_OUTPUT_DIR / "trace_net_trust_authority_quality.json"


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
    cur.execute("select to_regclass(%s) is not null as exists", (f"public.{table}",))
    return bool((cur.fetchone() or {}).get("exists"))


def collect_live_summary(database_url: str) -> Dict[str, Any]:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            summary: Dict[str, Any] = {}
            summary["pages"] = int(one(cur, "select count(*) from pages") or 0) if table_exists(cur, "pages") else 0
            summary["rag_candidate_records"] = int(one(cur, "select count(*) from rag_candidate_chunks") or 0) if table_exists(cur, "rag_candidate_chunks") else 0
            summary["trust_authority_records"] = int(one(cur, "select count(*) from trust_authority_records") or 0) if table_exists(cur, "trust_authority_records") else 0
            if table_exists(cur, "rag_candidate_chunks") and table_exists(cur, "trust_authority_records"):
                summary["missing_authority_records"] = int(one(cur, "select count(*) from rag_candidate_chunks c where not exists (select 1 from trust_authority_records a where a.candidate_id=c.candidate_id)") or 0)
                summary["missing_candidate_trust_tier"] = int(one(cur, "select count(*) from rag_candidate_chunks where trust_tier is null or btrim(trust_tier)='' ") or 0)
            else:
                summary["missing_authority_records"] = summary.get("rag_candidate_records", 0)
                summary["missing_candidate_trust_tier"] = 0
            if table_exists(cur, "trust_authority_records"):
                queries = {
                    "source_evidence_authority_records": "select count(*) from trust_authority_records where rag_bucket='source_evidence'",
                    "source_text_authority_records": "select count(*) from trust_authority_records where rag_bucket='source_text_evidence'",
                    "verified_part_authority_records": "select count(*) from trust_authority_records where rag_bucket='verified_part_evidence'",
                    "derived_context_authority_records": "select count(*) from trust_authority_records where rag_bucket='derived_context'",
                    "source_evidence_direct_answer_records": "select count(*) from trust_authority_records where rag_bucket='source_evidence' and can_answer_directly",
                    "derived_context_direct_answer_records": "select count(*) from trust_authority_records where rag_bucket='derived_context' and can_answer_directly",
                    "derived_context_canonical_source_truth_records": "select count(*) from trust_authority_records where rag_bucket='derived_context' and canonical_source_truth",
                    "unsafe_authority_records": "select count(*) from trust_authority_records where (not safe_for_rag) and (can_answer_directly or can_support_answer)",
                    "missing_source_url_authority_records": "select count(*) from trust_authority_records where safe_for_rag and (source_url is null or btrim(source_url)='')",
                    "source_truth_mutation_records": "select count(*) from trust_authority_records where source_truth_mutation_allowed",
                    "requires_citation_records": "select count(*) from trust_authority_records where requires_citation",
                    "requires_source_trace_records": "select count(*) from trust_authority_records where requires_source_trace",
                }
                for key, sql in queries.items():
                    summary[key] = int(one(cur, sql) or 0)
                cur.execute("select trust_scope, count(*) as n from trust_authority_records group by trust_scope")
                summary["trust_scope_counts"] = {str(r["trust_scope"]): int(r["n"]) for r in cur.fetchall()}
                cur.execute("select evidence_authority, count(*) as n from trust_authority_records group by evidence_authority")
                summary["evidence_authority_counts"] = {str(r["evidence_authority"]): int(r["n"]) for r in cur.fetchall()}
                cur.execute("select claim_authority, count(*) as n from trust_authority_records group by claim_authority")
                summary["claim_authority_counts"] = {str(r["claim_authority"]): int(r["n"]) for r in cur.fetchall()}
                cur.execute("select rag_role, count(*) as n from trust_authority_records group by rag_role")
                summary["rag_role_counts"] = {str(r["rag_role"]): int(r["n"]) for r in cur.fetchall()}
            summary.setdefault("source_truth_mutation_records", 0)
            return summary


def check(name: str, passed: bool, message: str) -> Dict[str, Any]:
    return {"name": name, "status": "OK" if passed else "FAIL", "message": message}


def run_quality(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Dict[str, Any]:
    def num(key: str, default: int = 0) -> int:
        try:
            return int(summary.get(key, default) or 0)
        except Exception:
            return default

    def th(key: str, default: Optional[int] = None) -> Optional[int]:
        val = thresholds.get(key, default)
        if val is None:
            return None
        return int(val)

    checks: List[Dict[str, Any]] = []
    checks.append(check("authority_records", num("trust_authority_records") >= th("min_authority_records", 1), f"authority_records={summary.get('trust_authority_records')}; minimum={th('min_authority_records',1)}"))
    checks.append(check("candidate_coverage", num("missing_authority_records") <= th("max_missing_authority_records", 0), f"missing_authority_records={summary.get('missing_authority_records')}; max={th('max_missing_authority_records',0)}"))
    checks.append(check("candidate_trust_tiers", num("missing_candidate_trust_tier") <= th("max_missing_candidate_trust_tier", 0), f"missing_candidate_trust_tier={summary.get('missing_candidate_trust_tier')}; max={th('max_missing_candidate_trust_tier',0)}"))
    checks.append(check("source_evidence_authority", num("source_evidence_authority_records") >= th("min_source_evidence_authority_records", 0), f"source_evidence={summary.get('source_evidence_authority_records')}; minimum={th('min_source_evidence_authority_records',0)}"))
    checks.append(check("source_text_authority", num("source_text_authority_records") >= th("min_source_text_authority_records", 0), f"source_text={summary.get('source_text_authority_records')}; minimum={th('min_source_text_authority_records',0)}"))
    checks.append(check("verified_part_authority", num("verified_part_authority_records") >= th("min_verified_part_authority_records", 0), f"verified_part={summary.get('verified_part_authority_records')}; minimum={th('min_verified_part_authority_records',0)}"))
    checks.append(check("derived_context_authority", num("derived_context_authority_records") >= th("min_derived_context_authority_records", 0), f"derived_context={summary.get('derived_context_authority_records')}; minimum={th('min_derived_context_authority_records',0)}"))
    checks.append(check("source_evidence_not_direct_answer", num("source_evidence_direct_answer_records") <= th("max_source_evidence_direct_answer_records", 0), f"source_evidence_direct_answer={summary.get('source_evidence_direct_answer_records')}; max={th('max_source_evidence_direct_answer_records',0)}"))
    checks.append(check("derived_context_not_direct_answer", num("derived_context_direct_answer_records") <= th("max_derived_context_direct_answer_records", 0), f"derived_context_direct_answer={summary.get('derived_context_direct_answer_records')}; max={th('max_derived_context_direct_answer_records',0)}"))
    checks.append(check("derived_context_not_canonical_source_truth", num("derived_context_canonical_source_truth_records") <= th("max_derived_context_canonical_source_truth_records", 0), f"derived_context_canonical={summary.get('derived_context_canonical_source_truth_records')}; max={th('max_derived_context_canonical_source_truth_records',0)}"))
    checks.append(check("unsafe_authority", num("unsafe_authority_records") <= th("max_unsafe_authority_records", 0), f"unsafe_authority={summary.get('unsafe_authority_records')}; max={th('max_unsafe_authority_records',0)}"))
    checks.append(check("missing_source_url_authority", num("missing_source_url_authority_records") <= th("max_missing_source_url_authority_records", 0), f"missing_source_url_authority={summary.get('missing_source_url_authority_records')}; max={th('max_missing_source_url_authority_records',0)}"))
    checks.append(check("source_truth_mutations", num("source_truth_mutation_records") <= th("max_source_truth_mutations", 0), f"source_truth_mutations={summary.get('source_truth_mutation_records')}; max={th('max_source_truth_mutations',0)}"))

    failed = [c for c in checks if c["status"] != "OK"]
    return {"status": "OK" if not failed else "FAIL", "summary": dict(summary), "checks": checks}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net trust authority quality")
    parser.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL", ""))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--quality", default=str(DEFAULT_QUALITY))
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-authority-records", type=int, default=1)
    parser.add_argument("--max-missing-authority-records", type=int, default=0)
    parser.add_argument("--max-missing-candidate-trust-tier", type=int, default=0)
    parser.add_argument("--min-source-evidence-authority-records", type=int, default=0)
    parser.add_argument("--min-source-text-authority-records", type=int, default=0)
    parser.add_argument("--min-verified-part-authority-records", type=int, default=0)
    parser.add_argument("--min-derived-context-authority-records", type=int, default=0)
    parser.add_argument("--max-source-evidence-direct-answer-records", type=int, default=0)
    parser.add_argument("--max-derived-context-direct-answer-records", type=int, default=0)
    parser.add_argument("--max-derived-context-canonical-source-truth-records", type=int, default=0)
    parser.add_argument("--max-unsafe-authority-records", type=int, default=0)
    parser.add_argument("--max-missing-source-url-authority-records", type=int, default=0)
    parser.add_argument("--max-source-truth-mutations", type=int, default=0)
    args = parser.parse_args(argv)

    summary = collect_live_summary(args.database_url) if args.database_url else load_json(Path(args.summary))
    report = run_quality(summary, vars(args))
    print("TRACE-Net trust authority quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for key in [
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
