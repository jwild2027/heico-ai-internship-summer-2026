"""Quality gate for TRACE-Net Postgres graph traversal audit v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_INPUT = Path("local_data/organization/trace_net/graph_audit/trace_net_graph_traversal_audit_summary.json")
DEFAULT_OUTPUT = Path("local_data/organization/trace_net/graph_audit/trace_net_graph_traversal_audit_quality.json")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")


def run_quality(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    def threshold_int(name: str, default: int) -> int:
        value = thresholds.get(name, default)
        if value is None:
            return default
        return int(value)

    check("pages", int(summary.get("postgres_pages") or 0) >= threshold_int("min_pages", 0), f"pages={summary.get('postgres_pages')}; minimum={threshold_int('min_pages',0)}")
    check("graph_nodes", int(summary.get("postgres_graph_nodes") or 0) >= threshold_int("min_graph_nodes", 0), f"nodes={summary.get('postgres_graph_nodes')}; minimum={threshold_int('min_graph_nodes',0)}")
    check("graph_edges", int(summary.get("postgres_graph_edges") or 0) >= threshold_int("min_graph_edges", 0), f"edges={summary.get('postgres_graph_edges')}; minimum={threshold_int('min_graph_edges',0)}")
    check("largest_component", int(summary.get("largest_component_nodes") or 0) >= threshold_int("min_largest_component_nodes", 0), f"largest={summary.get('largest_component_nodes')}; minimum={threshold_int('min_largest_component_nodes',0)}")
    check("orphan_edges", int(summary.get("graph_orphan_edges_sql") or 0) <= threshold_int("max_orphan_edges", 0), f"orphan_edges={summary.get('graph_orphan_edges_sql')}; max={threshold_int('max_orphan_edges',0)}")

    # Page-node coverage is useful when the graph loader has normalized page nodes.
    # It is optional for current mixed local-graph artifacts unless the caller sets a max.
    max_pages_without = thresholds.get("max_pages_without_graph_node")
    if max_pages_without is not None:
        check("pages_without_graph_node", int(summary.get("pages_without_graph_node") or 0) <= int(max_pages_without), f"pages_without_graph_node={summary.get('pages_without_graph_node')}; max={max_pages_without}")
    else:
        check("pages_without_graph_node_observed", True, f"pages_without_graph_node={summary.get('pages_without_graph_node')}; threshold not enforced")

    check("rag_candidates_without_page", int(summary.get("rag_candidates_without_page") or 0) <= threshold_int("max_rag_candidates_without_page", 0), f"rag_candidates_without_page={summary.get('rag_candidates_without_page')}; max={threshold_int('max_rag_candidates_without_page',0)}")
    check("citations_without_page", int(summary.get("citations_without_page") or 0) <= threshold_int("max_citations_without_page", 0), f"citations_without_page={summary.get('citations_without_page')}; max={threshold_int('max_citations_without_page',0)}")
    check("unsafe_rag_candidates", int(summary.get("unsafe_rag_candidate_records") or 0) <= threshold_int("max_unsafe_rag_candidates", 0), f"unsafe={summary.get('unsafe_rag_candidate_records')}; max={threshold_int('max_unsafe_rag_candidates',0)}")
    check("missing_source_urls", int(summary.get("rag_candidate_missing_source_url") or 0) <= threshold_int("max_missing_candidate_source_url", 0), f"missing_candidate_source_url={summary.get('rag_candidate_missing_source_url')}; max={threshold_int('max_missing_candidate_source_url',0)}")
    # Trust column is allowed to be incomplete for the current loader unless a threshold is provided.
    max_missing_trust = thresholds.get("max_missing_candidate_trust_tier")
    if max_missing_trust is not None:
        check("candidate_trust_tier_column", int(summary.get("rag_candidate_missing_trust_tier") or 0) <= int(max_missing_trust), f"missing_trust_tier={summary.get('rag_candidate_missing_trust_tier')}; max={max_missing_trust}")

    status = "OK" if all(c["ok"] for c in checks) else "FAIL"
    return {"status": status, "summary_path": str(DEFAULT_INPUT), **dict(summary), "checks": checks}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quality gate for TRACE-Net Postgres graph traversal audit.")
    parser.add_argument("--summary", default=str(DEFAULT_INPUT))
    parser.add_argument("--quality", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-pages", type=int, default=0)
    parser.add_argument("--min-graph-nodes", type=int, default=0)
    parser.add_argument("--min-graph-edges", type=int, default=0)
    parser.add_argument("--min-largest-component-nodes", type=int, default=0)
    parser.add_argument("--max-orphan-edges", type=int, default=0)
    parser.add_argument("--max-pages-without-graph-node", type=int)
    parser.add_argument("--max-rag-candidates-without-page", type=int, default=0)
    parser.add_argument("--max-citations-without-page", type=int, default=0)
    parser.add_argument("--max-unsafe-rag-candidates", type=int, default=0)
    parser.add_argument("--max-missing-candidate-source-url", type=int, default=0)
    parser.add_argument("--max-missing-candidate-trust-tier", type=int)
    args = parser.parse_args(argv)

    summary_path = Path(args.summary)
    if not summary_path.exists():
        raise SystemExit(f"Graph audit summary not found: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    thresholds = vars(args)
    report = run_quality(summary, thresholds)
    if args.write_json:
        _write_json(Path(args.quality), report)

    print("TRACE-Net graph traversal audit quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for key in ["postgres_pages", "postgres_graph_nodes", "postgres_graph_edges", "largest_component_nodes", "graph_orphan_edges_sql", "pages_without_graph_node", "unsafe_rag_candidate_records"]:
        print(f"    {key}: {report.get(key)}")
    print("  Checks:")
    for c in report["checks"]:
        print(f"    {'OK' if c['ok'] else 'FAIL'} {c['name']}: {c['detail']}")
    if args.write_json:
        print(f"\nJSON: {Path(args.quality)}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
