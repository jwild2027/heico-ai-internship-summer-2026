from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_SUMMARY = Path("local_data/organization/trace_net/page_context_overlay/trace_net_page_context_overlay_summary.json")
DEFAULT_QUALITY = Path("local_data/organization/trace_net/page_context_overlay/trace_net_page_context_overlay_quality.json")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "status": "OK" if ok else "FAIL", "detail": detail}


def run_quality(summary: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    def val(key: str, default: int = 0) -> int:
        try:
            return int(summary.get(key) if summary.get(key) is not None else default)
        except Exception:
            return default

    checks.append(check("status_ok", summary.get("status") == "OK", f"status={summary.get('status')}"))
    checks.append(check("context_records", val("postgres_page_context_records", val("context_records_loaded")) >= thresholds["min_context_records"], f"contexts={val('postgres_page_context_records', val('context_records_loaded'))}; minimum={thresholds['min_context_records']}"))
    checks.append(check("pages_with_context", val("pages_with_context_input") >= thresholds["min_pages_with_context"], f"pages_with_context={val('pages_with_context_input')}; minimum={thresholds['min_pages_with_context']}"))
    checks.append(check("context_graph_nodes", val("postgres_page_context_graph_nodes", val("context_graph_nodes_upserted")) >= thresholds["min_context_graph_nodes"], f"context_graph_nodes={val('postgres_page_context_graph_nodes', val('context_graph_nodes_upserted'))}; minimum={thresholds['min_context_graph_nodes']}"))
    checks.append(check("has_context_edges", val("postgres_has_context_edges", val("has_context_edges_upserted")) >= thresholds["min_has_context_edges"], f"has_context_edges={val('postgres_has_context_edges', val('has_context_edges_upserted'))}; minimum={thresholds['min_has_context_edges']}"))
    checks.append(check("tagged_as_edges", val("postgres_tagged_as_edges", val("tagged_as_edges_upserted")) >= thresholds["min_tagged_as_edges"], f"tagged_as_edges={val('postgres_tagged_as_edges', val('tagged_as_edges_upserted'))}; minimum={thresholds['min_tagged_as_edges']}"))
    checks.append(check("highlights_part_edges", val("postgres_highlights_part_edges", val("highlights_part_edges_upserted")) >= thresholds["min_highlights_part_edges"], f"highlights_part_edges={val('postgres_highlights_part_edges', val('highlights_part_edges_upserted'))}; minimum={thresholds['min_highlights_part_edges']}"))
    checks.append(check("missing_page_resolutions", val("missing_page_resolutions") <= thresholds["max_missing_page_resolutions"], f"missing_page_resolutions={val('missing_page_resolutions')}; max={thresholds['max_missing_page_resolutions']}"))
    checks.append(check("direct_answer_context", val("postgres_context_direct_answer_records", val("direct_answer_context_records")) <= thresholds["max_direct_answer_context_records"], f"direct_answer_context={val('postgres_context_direct_answer_records', val('direct_answer_context_records'))}; max={thresholds['max_direct_answer_context_records']}"))
    checks.append(check("canonical_source_truth_context", val("postgres_context_canonical_source_truth_records", val("canonical_source_truth_context_records")) <= thresholds["max_canonical_source_truth_context_records"], f"canonical_source_truth_context={val('postgres_context_canonical_source_truth_records', val('canonical_source_truth_context_records'))}; max={thresholds['max_canonical_source_truth_context_records']}"))
    checks.append(check("source_truth_mutations", val("source_truth_mutation_records") <= thresholds["max_source_truth_mutations"], f"source_truth_mutations={val('source_truth_mutation_records')}; max={thresholds['max_source_truth_mutations']}"))
    failures = [c for c in checks if c["status"] != "OK"]
    return {
        "status": "OK" if not failures else "FAIL",
        "summary": {
            "context_records": val("postgres_page_context_records", val("context_records_loaded")),
            "pages_with_context": val("pages_with_context_input"),
            "context_graph_nodes": val("postgres_page_context_graph_nodes", val("context_graph_nodes_upserted")),
            "has_context_edges": val("postgres_has_context_edges", val("has_context_edges_upserted")),
            "tagged_as_edges": val("postgres_tagged_as_edges", val("tagged_as_edges_upserted")),
            "highlights_part_edges": val("postgres_highlights_part_edges", val("highlights_part_edges_upserted")),
            "missing_page_resolutions": val("missing_page_resolutions"),
            "direct_answer_context_records": val("postgres_context_direct_answer_records", val("direct_answer_context_records")),
            "canonical_source_truth_context_records": val("postgres_context_canonical_source_truth_records", val("canonical_source_truth_context_records")),
            "source_truth_mutation_records": val("source_truth_mutation_records"),
        },
        "checks": checks,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Quality gate for TRACE-Net page context Postgres overlay.")
    p.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    p.add_argument("--quality", default=str(DEFAULT_QUALITY))
    p.add_argument("--min-context-records", type=int, default=1)
    p.add_argument("--min-pages-with-context", type=int, default=1)
    p.add_argument("--min-context-graph-nodes", type=int, default=1)
    p.add_argument("--min-has-context-edges", type=int, default=1)
    p.add_argument("--min-tagged-as-edges", type=int, default=0)
    p.add_argument("--min-highlights-part-edges", type=int, default=0)
    p.add_argument("--max-missing-page-resolutions", type=int, default=0)
    p.add_argument("--max-direct-answer-context-records", type=int, default=0)
    p.add_argument("--max-canonical-source-truth-context-records", type=int, default=0)
    p.add_argument("--max-source-truth-mutations", type=int, default=0)
    p.add_argument("--write-json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = load_json(Path(args.summary))
    thresholds = {
        "min_context_records": args.min_context_records,
        "min_pages_with_context": args.min_pages_with_context,
        "min_context_graph_nodes": args.min_context_graph_nodes,
        "min_has_context_edges": args.min_has_context_edges,
        "min_tagged_as_edges": args.min_tagged_as_edges,
        "min_highlights_part_edges": args.min_highlights_part_edges,
        "max_missing_page_resolutions": args.max_missing_page_resolutions,
        "max_direct_answer_context_records": args.max_direct_answer_context_records,
        "max_canonical_source_truth_context_records": args.max_canonical_source_truth_context_records,
        "max_source_truth_mutations": args.max_source_truth_mutations,
    }
    report = run_quality(summary, thresholds)
    print("TRACE-Net page context overlay quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for k, v in report["summary"].items():
        print(f"    {k}: {v}")
    print("  Checks:")
    for c in report["checks"]:
        print(f"    {c['status']} {c['name']}: {c['detail']}")
    if args.write_json:
        qpath = Path(args.quality)
        qpath.parent.mkdir(parents=True, exist_ok=True)
        qpath.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nJSON: {qpath}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
