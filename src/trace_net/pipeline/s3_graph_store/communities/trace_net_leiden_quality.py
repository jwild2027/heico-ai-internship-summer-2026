"""Quality gate for TRACE-Net Leiden/community overlay."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import argparse
import json
import sys

DEFAULT_COMMUNITY_DIR = Path("local_data/organization/communities")


@dataclass(frozen=True)
class LeidenQualityPaths:
    community_dir: Path = DEFAULT_COMMUNITY_DIR

    @property
    def summary_path(self) -> Path:
        return self.community_dir / "leiden_community_summary.json"

    @property
    def communities_jsonl_path(self) -> Path:
        return self.community_dir / "leiden_communities.jsonl"

    @property
    def projection_nodes_path(self) -> Path:
        return self.community_dir / "semantic_projection_nodes.json"

    @property
    def projection_edges_path(self) -> Path:
        return self.community_dir / "semantic_projection_edges.json"

    @property
    def graph_nodes_path(self) -> Path:
        return self.community_dir / "leiden_graph_nodes.json"

    @property
    def graph_edges_path(self) -> Path:
        return self.community_dir / "leiden_graph_edges.json"

    @property
    def quality_path(self) -> Path:
        return self.community_dir / "leiden_community_quality.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            count += 1
    return count


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def build_leiden_quality(
    paths: LeidenQualityPaths,
    *,
    min_pages: int = 1,
    min_communities: int = 1,
    min_projection_edges: int = 1,
    require_leiden: bool = False,
) -> dict[str, Any]:
    summary = _read_json(paths.summary_path, {})
    communities_jsonl_count = _count_jsonl(paths.communities_jsonl_path)
    projection_nodes = _read_json(paths.projection_nodes_path, [])
    projection_edges = _read_json(paths.projection_edges_path, [])
    graph_nodes = _read_json(paths.graph_nodes_path, [])
    graph_edges = _read_json(paths.graph_edges_path, [])

    quality_summary = {
        "leiden_summary_present": paths.summary_path.exists(),
        "leiden_communities_present": paths.communities_jsonl_path.exists(),
        "leiden_projection_present": paths.projection_nodes_path.exists() and paths.projection_edges_path.exists(),
        "leiden_status": summary.get("status"),
        "leiden_requested_algorithm": summary.get("requested_algorithm"),
        "leiden_algorithm_used": summary.get("algorithm_used"),
        "leiden_available": bool(summary.get("leiden_available")),
        "leiden_pages_loaded": int(summary.get("pages_loaded") or 0),
        "leiden_projection_nodes": int(summary.get("projection_nodes") or len(projection_nodes or [])),
        "leiden_projection_edges": int(summary.get("projection_edges") or len(projection_edges or [])),
        "leiden_community_count": int(summary.get("community_count") or 0),
        "leiden_communities_jsonl_count": communities_jsonl_count,
        "leiden_communities_with_pages": int(summary.get("communities_with_pages") or 0),
        "leiden_largest_community_pages": int(summary.get("largest_community_pages") or 0),
        "leiden_overlay_nodes": int(summary.get("overlay_nodes") or len(graph_nodes or [])),
        "leiden_overlay_edges": int(summary.get("overlay_edges") or len(graph_edges or [])),
        "leiden_require_leiden": require_leiden,
    }

    checks = [
        _check(
            "leiden_artifacts_present",
            quality_summary["leiden_summary_present"] and quality_summary["leiden_communities_present"],
            f"summary={quality_summary['leiden_summary_present']}; communities={quality_summary['leiden_communities_present']}.",
        ),
        _check(
            "leiden_status",
            str(quality_summary["leiden_status"]).upper() == "OK",
            f"status={quality_summary['leiden_status']}.",
        ),
        _check(
            "leiden_pages",
            quality_summary["leiden_pages_loaded"] >= min_pages,
            f"pages_loaded={quality_summary['leiden_pages_loaded']}; minimum={min_pages}.",
        ),
        _check(
            "leiden_projection_edges",
            quality_summary["leiden_projection_edges"] >= min_projection_edges,
            f"projection_edges={quality_summary['leiden_projection_edges']}; minimum={min_projection_edges}.",
        ),
        _check(
            "leiden_communities",
            quality_summary["leiden_community_count"] >= min_communities
            and quality_summary["leiden_communities_jsonl_count"] >= min_communities,
            f"communities={quality_summary['leiden_community_count']}; jsonl={quality_summary['leiden_communities_jsonl_count']}; minimum={min_communities}.",
        ),
        _check(
            "leiden_communities_with_pages",
            quality_summary["leiden_communities_with_pages"] >= 1,
            f"communities_with_pages={quality_summary['leiden_communities_with_pages']}.",
        ),
        _check(
            "leiden_overlay_graph",
            quality_summary["leiden_overlay_nodes"] >= quality_summary["leiden_community_count"]
            and quality_summary["leiden_overlay_edges"] >= quality_summary["leiden_pages_loaded"],
            f"overlay_nodes={quality_summary['leiden_overlay_nodes']}; overlay_edges={quality_summary['leiden_overlay_edges']}.",
        ),
        _check(
            "leiden_algorithm_available",
            (not require_leiden) or quality_summary["leiden_available"],
            f"algorithm_used={quality_summary['leiden_algorithm_used']}; leiden_available={quality_summary['leiden_available']}; require_leiden={require_leiden}.",
        ),
    ]
    status = "OK" if all(c["ok"] for c in checks) else "FAIL"
    return {"status": status, "summary": quality_summary, "checks": checks}


def _print_report(report: dict[str, Any], paths: LeidenQualityPaths) -> None:
    print("TRACE-Net Leiden/community quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for k, v in report["summary"].items():
        print(f"    {k}: {v}")
    print("  Checks:")
    for check in report["checks"]:
        prefix = "OK" if check["ok"] else "FAIL"
        print(f"    {prefix} {check['name']}: {check['detail']}")
    print(f"\nJSON: {paths.quality_path}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Leiden/community overlay quality.")
    parser.add_argument("--community-dir", default=str(DEFAULT_COMMUNITY_DIR))
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-communities", type=int, default=1)
    parser.add_argument("--min-projection-edges", type=int, default=1)
    parser.add_argument("--require-leiden", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    paths = LeidenQualityPaths(community_dir=Path(args.community_dir))
    report = build_leiden_quality(
        paths,
        min_pages=args.min_pages,
        min_communities=args.min_communities,
        min_projection_edges=args.min_projection_edges,
        require_leiden=args.require_leiden,
    )
    if args.write_json:
        paths.quality_path.parent.mkdir(parents=True, exist_ok=True)
        paths.quality_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_report(report, paths)
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
