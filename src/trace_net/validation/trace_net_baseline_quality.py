"""Quality gate for TRACE-Net pre-algorithm baseline metrics v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_SUMMARY = Path("local_data/organization/trace_net/baseline/pre_algorithm_filter_v1/trace_net_pre_algorithm_baseline_summary.json")
DEFAULT_QUALITY = Path("local_data/organization/trace_net/baseline/pre_algorithm_filter_v1/trace_net_pre_algorithm_baseline_quality.json")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")


def run_quality(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("pages", int(summary.get("pages") or 0) >= int(thresholds.get("min_pages", 0)), f"pages={summary.get('pages')}; minimum={thresholds.get('min_pages',0)}")
    check("ocr_records", int(summary.get("ocr_records") or 0) >= int(thresholds.get("min_ocr_records", 0)), f"ocr_records={summary.get('ocr_records')}; minimum={thresholds.get('min_ocr_records',0)}")
    check("ocr_text_records", int(summary.get("ocr_text_records") or 0) >= int(thresholds.get("min_ocr_text_records", 0)), f"ocr_text_records={summary.get('ocr_text_records')}; minimum={thresholds.get('min_ocr_text_records',0)}")
    check("graph_nodes", int(summary.get("graph_nodes") or 0) >= int(thresholds.get("min_graph_nodes", 0)), f"graph_nodes={summary.get('graph_nodes')}; minimum={thresholds.get('min_graph_nodes',0)}")
    check("graph_edges", int(summary.get("graph_edges") or 0) >= int(thresholds.get("min_graph_edges", 0)), f"graph_edges={summary.get('graph_edges')}; minimum={thresholds.get('min_graph_edges',0)}")
    check("graph_orphan_edges", int(summary.get("graph_orphan_edges") or 0) <= int(thresholds.get("max_graph_orphan_edges", 0)), f"orphan_edges={summary.get('graph_orphan_edges')}; max={thresholds.get('max_graph_orphan_edges',0)}")
    check("rag_candidate_records", int(summary.get("rag_candidate_records") or 0) >= int(thresholds.get("min_rag_candidates", 0)), f"rag_candidates={summary.get('rag_candidate_records')}; minimum={thresholds.get('min_rag_candidates',0)}")
    check("unsafe_rag_candidates", int(summary.get("rag_candidate_unsafe_records") or 0) <= int(thresholds.get("max_unsafe_rag_candidates", 0)), f"unsafe={summary.get('rag_candidate_unsafe_records')}; max={thresholds.get('max_unsafe_rag_candidates',0)}")
    check("missing_candidate_source_url", int(summary.get("rag_candidate_missing_source_url") or 0) <= int(thresholds.get("max_missing_candidate_source_url", 0)), f"missing_candidate_source_url={summary.get('rag_candidate_missing_source_url')}; max={thresholds.get('max_missing_candidate_source_url',0)}")
    check("citations", int(summary.get("source_citations") or 0) >= int(thresholds.get("min_citations", 0)), f"citations={summary.get('source_citations')}; minimum={thresholds.get('min_citations',0)}")
    check("missing_citation_source_url", int(summary.get("citations_missing_source_url") or 0) <= int(thresholds.get("max_missing_citation_source_url", 0)), f"missing_citation_source_url={summary.get('citations_missing_source_url')}; max={thresholds.get('max_missing_citation_source_url',0)}")
    max_missing_trust = thresholds.get("max_missing_candidate_trust_tier")
    if max_missing_trust is not None:
        check("missing_candidate_trust_tier", int(summary.get("rag_candidate_missing_trust_tier") or 0) <= int(max_missing_trust), f"missing_candidate_trust_tier={summary.get('rag_candidate_missing_trust_tier')}; max={max_missing_trust}")
    return {"status": "OK" if all(c["ok"] for c in checks) else "FAIL", **dict(summary), "checks": checks}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quality gate for TRACE-Net pre-algorithm baseline metrics.")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--quality", default=str(DEFAULT_QUALITY))
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-pages", type=int, default=0)
    parser.add_argument("--min-ocr-records", type=int, default=0)
    parser.add_argument("--min-ocr-text-records", type=int, default=0)
    parser.add_argument("--min-graph-nodes", type=int, default=0)
    parser.add_argument("--min-graph-edges", type=int, default=0)
    parser.add_argument("--max-graph-orphan-edges", type=int, default=0)
    parser.add_argument("--min-rag-candidates", type=int, default=0)
    parser.add_argument("--max-unsafe-rag-candidates", type=int, default=0)
    parser.add_argument("--max-missing-candidate-source-url", type=int, default=0)
    parser.add_argument("--max-missing-candidate-trust-tier", type=int)
    parser.add_argument("--min-citations", type=int, default=0)
    parser.add_argument("--max-missing-citation-source-url", type=int, default=0)
    args = parser.parse_args(argv)

    summary_path = Path(args.summary)
    if not summary_path.exists():
        raise SystemExit(f"Baseline summary not found: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report = run_quality(summary, vars(args))
    if args.write_json:
        _write_json(Path(args.quality), report)
    print("TRACE-Net pre-algorithm baseline quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for key in ["pages", "ocr_records", "ocr_text_records", "graph_nodes", "graph_edges", "rag_candidate_records", "rag_candidate_unsafe_records", "source_citations"]:
        print(f"    {key}: {report.get(key)}")
    print("  Checks:")
    for c in report["checks"]:
        print(f"    {'OK' if c['ok'] else 'FAIL'} {c['name']}: {c['detail']}")
    if args.write_json:
        print(f"\nJSON: {Path(args.quality)}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
