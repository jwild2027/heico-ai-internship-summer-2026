from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

VERSION = "trace_net_graph_explorer_quality_v1_3_context_overlay"
DEFAULT_DIR = Path("local_data/organization/trace_net/graph_explorer")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def run_quality(summary: Dict[str, Any], thresholds: Dict[str, Any], html_path: Path, data_path: Path) -> Dict[str, Any]:
    checks = []
    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "status": "OK" if ok else "FAIL", "detail": detail})

    node_type_counts = summary.get("node_type_counts") or {}
    edge_type_counts = summary.get("edge_type_counts") or {}
    nodes = int(summary.get("nodes") or 0)
    edges = int(summary.get("edges") or 0)
    pages = int(summary.get("page_nodes") or node_type_counts.get("page") or 0)
    parts = int(summary.get("part_nodes") or node_type_counts.get("part") or 0)
    candidates = int(summary.get("candidate_nodes") or node_type_counts.get("candidate") or 0)
    citations = int(summary.get("citation_nodes") or node_type_counts.get("citation") or 0)
    contexts = int(summary.get("page_context_nodes") or node_type_counts.get("page_context") or 0)

    check("artifacts_present", html_path.exists() and data_path.exists(), f"html={html_path.exists()}; data={data_path.exists()}")
    check("nodes", nodes >= int(thresholds.get("min_nodes", 1)), f"nodes={nodes}; minimum={thresholds.get('min_nodes')}")
    check("edges", edges >= int(thresholds.get("min_edges", 1)), f"edges={edges}; minimum={thresholds.get('min_edges')}")
    check("pages", pages >= int(thresholds.get("min_pages", 1)), f"page_nodes={pages}; minimum={thresholds.get('min_pages')}")
    check("part_nodes", parts >= int(thresholds.get("min_part_nodes", 1)), f"part_nodes={parts}; minimum={thresholds.get('min_part_nodes')}")
    check("candidate_nodes", candidates >= int(thresholds.get("min_candidate_nodes", 1)), f"candidate_nodes={candidates}; minimum={thresholds.get('min_candidate_nodes')}")
    check("citation_nodes", citations >= int(thresholds.get("min_citation_nodes", 0)), f"citation_nodes={citations}; minimum={thresholds.get('min_citation_nodes')}")
    check("candidate_edges", int(edge_type_counts.get("HAS_CANDIDATE") or 0) >= int(thresholds.get("min_has_candidate_edges", 1)), f"HAS_CANDIDATE={edge_type_counts.get('HAS_CANDIDATE')}; minimum={thresholds.get('min_has_candidate_edges')}")
    check("part_page_edges", int(edge_type_counts.get("PART_ON_PAGE") or 0) >= int(thresholds.get("min_part_page_edges", 1)), f"PART_ON_PAGE={edge_type_counts.get('PART_ON_PAGE')}; minimum={thresholds.get('min_part_page_edges')}")
    check("trust_edges", int(edge_type_counts.get("HAS_TRUST_TRAIT") or 0) >= int(thresholds.get("min_trust_edges", 1)), f"HAS_TRUST_TRAIT={edge_type_counts.get('HAS_TRUST_TRAIT')}; minimum={thresholds.get('min_trust_edges')}")
    check("context_nodes", contexts >= int(thresholds.get("min_context_nodes", 0)), f"page_context_nodes={contexts}; minimum={thresholds.get('min_context_nodes')}")
    check("has_context_edges", int(edge_type_counts.get("HAS_CONTEXT") or 0) >= int(thresholds.get("min_has_context_edges", 0)), f"HAS_CONTEXT={edge_type_counts.get('HAS_CONTEXT')}; minimum={thresholds.get('min_has_context_edges')}")
    if thresholds.get("require_html_text"):
        text = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
        check("html_contains_app", "TRACE-Net Graph Explorer" in text and "Click any node" in text, "HTML contains expected app text")

    status = "OK" if all(c["status"] == "OK" for c in checks) else "FAIL"
    return {
        "status": status,
        "version": VERSION,
        "summary": {
            "graph_explorer_nodes": nodes,
            "graph_explorer_edges": edges,
            "graph_explorer_page_nodes": pages,
            "graph_explorer_part_nodes": parts,
            "graph_explorer_candidate_nodes": candidates,
            "graph_explorer_citation_nodes": citations,
            "graph_explorer_context_nodes": contexts,
            "graph_explorer_node_type_counts": node_type_counts,
            "graph_explorer_edge_type_counts": edge_type_counts,
            "graph_explorer_html_path": str(html_path),
            "graph_explorer_data_path": str(data_path),
        },
        "checks": checks,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Quality gate for TRACE-Net graph explorer artifacts.")
    parser.add_argument("--summary", default=str(DEFAULT_DIR / "trace_net_graph_explorer_summary.json"))
    parser.add_argument("--html", default=str(DEFAULT_DIR / "trace_net_graph_explorer.html"))
    parser.add_argument("--data", default=str(DEFAULT_DIR / "trace_net_graph_explorer_data.json"))
    parser.add_argument("--quality", default=str(DEFAULT_DIR / "trace_net_graph_explorer_quality.json"))
    parser.add_argument("--min-nodes", type=int, default=1)
    parser.add_argument("--min-edges", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-part-nodes", type=int, default=1)
    parser.add_argument("--min-candidate-nodes", type=int, default=1)
    parser.add_argument("--min-citation-nodes", type=int, default=0)
    parser.add_argument("--min-has-candidate-edges", type=int, default=1)
    parser.add_argument("--min-part-page-edges", type=int, default=1)
    parser.add_argument("--min-trust-edges", type=int, default=1)
    parser.add_argument("--min-context-nodes", type=int, default=0)
    parser.add_argument("--min-has-context-edges", type=int, default=0)
    parser.add_argument("--require-html-text", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    summary = _load_json(Path(args.summary))
    thresholds = vars(args)
    report = run_quality(summary, thresholds, Path(args.html), Path(args.data))
    print("TRACE-Net graph explorer quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for key, value in report["summary"].items():
        if key.endswith("counts"):
            print(f"    {key}: {value}")
        else:
            print(f"    {key}: {value}")
    print("  Checks:")
    for c in report["checks"]:
        print(f"    {c['status']} {c['name']}: {c['detail']}")
    if args.write_json:
        path = Path(args.quality)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON: {path}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
