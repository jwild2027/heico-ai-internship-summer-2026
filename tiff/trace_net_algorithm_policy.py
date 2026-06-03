"""TRACE-Net algorithm policy builder.

This module turns measured community-ablation results into a small reusable
policy/config artifact.  The policy answers questions such as:

* Which algorithm should TRACE-Net use for repair batching?
* Which algorithm should broad retrieval expansion use?
* Which jobs should bypass communities and use deterministic graph traversal?

The artifact is intentionally conservative: exact source-tracing and source-of-
truth lookups always use deterministic graph traversal, regardless of community
metrics.  Community algorithms are only selected for jobs where they measured
well or are operationally appropriate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_COMMUNITY_DIR = Path("local_data/organization/communities")


@dataclass(frozen=True)
class AlgorithmPolicyPaths:
    community_dir: Path = DEFAULT_COMMUNITY_DIR

    @property
    def ablation_eval_path(self) -> Path:
        return self.community_dir / "community_ablation_eval.json"

    @property
    def policy_path(self) -> Path:
        return self.community_dir / "community_algorithm_policy.json"

    @property
    def policy_report_path(self) -> Path:
        return self.community_dir / "community_algorithm_policy_report.md"

    @property
    def quality_path(self) -> Path:
        return self.community_dir / "community_algorithm_policy_quality.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _algorithm_by_name(report: Mapping[str, Any], name: str) -> dict[str, Any]:
    for item in _as_list(report.get("algorithms")):
        if isinstance(item, dict) and item.get("algorithm") == name:
            return item
    return {}


def _available_algorithm_names(report: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for item in _as_list(report.get("algorithms")):
        if isinstance(item, dict) and item.get("algorithm_available", True):
            name = str(item.get("algorithm") or "")
            if name:
                names.append(name)
    return names


def _metric(report: Mapping[str, Any], algorithm: str, metric: str) -> float | None:
    alg = _algorithm_by_name(report, algorithm)
    return _safe_float(alg.get(metric), None)


def _score(report: Mapping[str, Any], algorithm: str, score_key: str) -> float | None:
    return _metric(report, algorithm, score_key)


def _best_algorithm(report: Mapping[str, Any], summary_key: str, fallback: str) -> str:
    summary = _as_dict(report.get("summary"))
    best = str(summary.get(summary_key) or "")
    if best:
        return best
    return fallback


def _score_for_selected(report: Mapping[str, Any], algorithm: str, score_key: str) -> float | None:
    return _score(report, algorithm, score_key)


def _delta(report: Mapping[str, Any], left: str, right: str, score_key: str) -> float | None:
    a = _score(report, left, score_key)
    b = _score(report, right, score_key)
    if a is None or b is None:
        return None
    return round(a - b, 6)


def _job(
    *,
    selected_algorithm: str,
    reason: str,
    algorithm_family: str,
    score: float | None = None,
    backup_algorithm: str | None = None,
    allowed_algorithms: list[str] | None = None,
    disallowed_algorithms: list[str] | None = None,
    source_of_truth: bool = False,
    uses_communities: bool = False,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "selected_algorithm": selected_algorithm,
        "backup_algorithm": backup_algorithm,
        "algorithm_family": algorithm_family,
        "score": score,
        "reason": reason,
        "allowed_algorithms": allowed_algorithms or [selected_algorithm],
        "disallowed_algorithms": disallowed_algorithms or [],
        "source_of_truth": bool(source_of_truth),
        "uses_communities": bool(uses_communities),
        "notes": notes or [],
    }


def build_algorithm_policy(
    ablation_report: Mapping[str, Any],
    *,
    require_leiden_for_retrieval: bool = False,
    write_source_path: str | None = None,
) -> dict[str, Any]:
    """Build a TRACE-Net algorithm policy from ablation metrics."""
    summary = _as_dict(ablation_report.get("summary"))
    available = _available_algorithm_names(ablation_report)

    repair_algorithm = _best_algorithm(ablation_report, "best_repair_batching_algorithm", "route_grouping")
    retrieval_algorithm = _best_algorithm(ablation_report, "best_retrieval_expansion_algorithm", "leiden")

    leiden_available = bool(summary.get("leiden_available")) or "leiden" in available
    if require_leiden_for_retrieval and not leiden_available:
        retrieval_algorithm = "route_grouping"

    repair_score = _score_for_selected(ablation_report, repair_algorithm, "repair_batching_score")
    retrieval_score = _score_for_selected(ablation_report, retrieval_algorithm, "retrieval_expansion_score")

    route_repair_score = _score(ablation_report, "route_grouping", "repair_batching_score")
    leiden_retrieval_score = _score(ablation_report, "leiden", "retrieval_expansion_score")

    source_trace_notes = [
        "Exact source tracing must use deterministic graph traversal, not community expansion.",
        "Communities may suggest related neighborhoods but cannot prove source evidence.",
    ]

    jobs: dict[str, dict[str, Any]] = {
        "exact_part_lookup": _job(
            selected_algorithm="deterministic_graph_traversal",
            backup_algorithm="exact_keyword_catalog_lookup",
            algorithm_family="source_trace",
            reason="Exact part lookup needs source-proof paths through Part -> PartMention -> Page -> Source.",
            source_of_truth=True,
            uses_communities=False,
            disallowed_algorithms=["leiden", "networkx_greedy_modularity", "route_grouping"],
            notes=source_trace_notes,
        ),
        "exact_page_lookup": _job(
            selected_algorithm="deterministic_graph_traversal",
            backup_algorithm="page_index_lookup",
            algorithm_family="source_trace",
            reason="Exact page lookup should resolve Page -> Document/ATA/Source/TIFF/OCR directly.",
            source_of_truth=True,
            uses_communities=False,
            disallowed_algorithms=["leiden", "networkx_greedy_modularity", "route_grouping"],
            notes=source_trace_notes,
        ),
        "source_trace": _job(
            selected_algorithm="deterministic_graph_traversal",
            backup_algorithm="source_link_index_lookup",
            algorithm_family="source_trace",
            reason="Source evidence must remain deterministic and auditable.",
            source_of_truth=True,
            uses_communities=False,
            disallowed_algorithms=["leiden", "networkx_greedy_modularity", "route_grouping"],
            notes=source_trace_notes,
        ),
        "trace_net_repair_batching": _job(
            selected_algorithm=repair_algorithm,
            backup_algorithm="route_grouping" if repair_algorithm != "route_grouping" else "deterministic_graph_traversal",
            algorithm_family="operational_batching",
            score=repair_score,
            reason="Selected by best repair_batching_score from community ablation metrics.",
            source_of_truth=False,
            uses_communities=repair_algorithm not in {"route_grouping", "no_community"},
            allowed_algorithms=["route_grouping", "leiden", "networkx_greedy_modularity", "no_community"],
            notes=[
                f"route_grouping repair score={route_repair_score}",
                f"selected repair score={repair_score}",
                "Use this for queues like table extraction, cleanup repair, OCR validation, and human review batching.",
            ],
        ),
        "table_extraction_batching": _job(
            selected_algorithm="route_grouping",
            backup_algorithm=repair_algorithm,
            algorithm_family="operational_batching",
            score=route_repair_score,
            reason="Table extraction follows explicit TRACE-Net routes and gates; route grouping is intentionally preferred.",
            source_of_truth=False,
            uses_communities=False,
            allowed_algorithms=["route_grouping"],
            notes=[
                "Use table_high/table_medium/table_candidate_review/skip_non_table rather than Leiden for execution queues.",
                "Graph and layout gates remain the final check before cutting or OCR.",
            ],
        ),
        "review_queue_batching": _job(
            selected_algorithm=repair_algorithm,
            backup_algorithm="leiden" if leiden_available else "route_grouping",
            algorithm_family="operational_batching",
            score=repair_score,
            reason="Human review should batch by repair route first; Leiden can be used inside a route for secondary grouping.",
            source_of_truth=False,
            uses_communities=repair_algorithm == "leiden",
            allowed_algorithms=["route_grouping", "leiden", "networkx_greedy_modularity"],
            notes=[
                "Primary grouping: route/trust/review traits.",
                "Secondary grouping: Leiden community inside each route when helpful.",
            ],
        ),
        "broad_retrieval_expansion": _job(
            selected_algorithm=retrieval_algorithm,
            backup_algorithm="route_grouping" if retrieval_algorithm != "route_grouping" else "deterministic_graph_traversal",
            algorithm_family="semantic_neighborhood",
            score=retrieval_score,
            reason="Selected by best retrieval_expansion_score from community ablation metrics.",
            source_of_truth=False,
            uses_communities=retrieval_algorithm in {"leiden", "networkx_greedy_modularity"},
            allowed_algorithms=["leiden", "route_grouping", "networkx_greedy_modularity", "no_community"],
            notes=[
                f"leiden retrieval score={leiden_retrieval_score}",
                f"selected retrieval score={retrieval_score}",
                "Use only to expand candidates; every answer still needs deterministic source trace.",
            ],
        ),
        "community_summaries": _job(
            selected_algorithm="leiden" if leiden_available else retrieval_algorithm,
            backup_algorithm="networkx_greedy_modularity" if not leiden_available else "route_grouping",
            algorithm_family="semantic_neighborhood",
            score=leiden_retrieval_score if leiden_available else retrieval_score,
            reason="Community summaries should use semantic neighborhoods; prefer Leiden when available.",
            source_of_truth=False,
            uses_communities=True,
            allowed_algorithms=["leiden", "networkx_greedy_modularity", "route_grouping"],
            notes=[
                "Community summaries are exploration aids, not evidence proof.",
                "Each community summary must retain source page IDs.",
            ],
        ),
        "cross_document_exploration_future": _job(
            selected_algorithm="leiden" if leiden_available else "networkx_greedy_modularity",
            backup_algorithm="route_grouping",
            algorithm_family="semantic_neighborhood",
            score=leiden_retrieval_score if leiden_available else None,
            reason="Cross-document relatedness benefits from semantic communities once multiple documents exist.",
            source_of_truth=False,
            uses_communities=True,
            allowed_algorithms=["leiden", "networkx_greedy_modularity"],
            notes=[
                "Only relevant when more than one document/manual has been ingested.",
                "Use canonical bridge nodes like parts, ATA codes, topics, and traits.",
            ],
        ),
    }

    policy = {
        "status": "OK",
        "created_at": _utc_now(),
        "policy_version": "trace_net_algorithm_policy_v1",
        "source_ablation_report": write_source_path,
        "summary": {
            "pages_loaded": summary.get("pages_loaded"),
            "projection_nodes": summary.get("projection_nodes"),
            "projection_edges": summary.get("projection_edges"),
            "available_algorithms": available,
            "leiden_available": leiden_available,
            "best_repair_batching_algorithm": repair_algorithm,
            "best_repair_batching_score": repair_score,
            "best_retrieval_expansion_algorithm": retrieval_algorithm,
            "best_retrieval_expansion_score": retrieval_score,
            "leiden_vs_route_repair_delta": summary.get("leiden_vs_route_repair_delta"),
            "leiden_vs_route_retrieval_delta": summary.get("leiden_vs_route_retrieval_delta"),
            "policy_repair_batching_algorithm": jobs["trace_net_repair_batching"]["selected_algorithm"],
            "policy_retrieval_expansion_algorithm": jobs["broad_retrieval_expansion"]["selected_algorithm"],
            "policy_source_trace_algorithm": jobs["source_trace"]["selected_algorithm"],
        },
        "jobs": jobs,
        "rules": [
            {
                "rule": "source_trace_never_uses_communities",
                "detail": "Exact page, part, and source-trace jobs use deterministic graph traversal regardless of community scores.",
            },
            {
                "rule": "repair_uses_best_batching_metric",
                "detail": "TRACE-Net repair/review queues use the measured best repair-batching algorithm, currently route_grouping in the 509-page run.",
            },
            {
                "rule": "retrieval_uses_best_expansion_metric",
                "detail": "Broad retrieval expansion uses the measured best retrieval-expansion algorithm, currently Leiden in the 509-page run.",
            },
            {
                "rule": "communities_expand_candidates_only",
                "detail": "Leiden/other communities may expand candidates but cannot prove final answers without source-trace paths.",
            },
        ],
        "algorithms": _as_list(ablation_report.get("algorithms")),
    }
    return policy


def render_algorithm_policy_markdown(policy: Mapping[str, Any]) -> str:
    summary = _as_dict(policy.get("summary"))
    jobs = _as_dict(policy.get("jobs"))
    lines: list[str] = []
    lines.append("# TRACE-Net Algorithm Policy")
    lines.append("")
    lines.append(f"Status: **{policy.get('status', 'UNKNOWN')}**")
    lines.append(f"Policy version: `{policy.get('policy_version')}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for key in (
        "pages_loaded",
        "projection_nodes",
        "projection_edges",
        "leiden_available",
        "best_repair_batching_algorithm",
        "best_repair_batching_score",
        "best_retrieval_expansion_algorithm",
        "best_retrieval_expansion_score",
        "leiden_vs_route_repair_delta",
        "leiden_vs_route_retrieval_delta",
        "policy_repair_batching_algorithm",
        "policy_retrieval_expansion_algorithm",
        "policy_source_trace_algorithm",
    ):
        lines.append(f"- `{key}`: {summary.get(key)}")
    lines.append("")
    lines.append("## Job Policy")
    lines.append("")
    lines.append("| Job | Selected algorithm | Family | Score | Uses communities | Source of truth |")
    lines.append("|---|---|---|---:|---:|---:|")
    for job_name in sorted(jobs):
        job = _as_dict(jobs.get(job_name))
        lines.append(
            f"| `{job_name}` | `{job.get('selected_algorithm')}` | `{job.get('algorithm_family')}` | {job.get('score')} | {job.get('uses_communities')} | {job.get('source_of_truth')} |"
        )
    lines.append("")
    lines.append("## Rationale")
    lines.append("")
    for job_name in sorted(jobs):
        job = _as_dict(jobs.get(job_name))
        lines.append(f"### `{job_name}`")
        lines.append("")
        lines.append(f"Selected: `{job.get('selected_algorithm')}`")
        if job.get("backup_algorithm"):
            lines.append(f"Backup: `{job.get('backup_algorithm')}`")
        lines.append(f"Reason: {job.get('reason')}")
        notes = _as_list(job.get("notes"))
        if notes:
            lines.append("Notes:")
            for note in notes:
                lines.append(f"- {note}")
        lines.append("")
    lines.append("## Rules")
    lines.append("")
    for rule in _as_list(policy.get("rules")):
        if isinstance(rule, dict):
            lines.append(f"- **{rule.get('rule')}**: {rule.get('detail')}")
    lines.append("")
    return "\n".join(lines)


def build_and_write_algorithm_policy(
    paths: AlgorithmPolicyPaths | None = None,
    *,
    require_leiden_for_retrieval: bool = False,
) -> dict[str, Any]:
    paths = paths or AlgorithmPolicyPaths()
    ablation = _as_dict(_read_json(paths.ablation_eval_path, default={}))
    policy = build_algorithm_policy(
        ablation,
        require_leiden_for_retrieval=require_leiden_for_retrieval,
        write_source_path=str(paths.ablation_eval_path),
    )
    _write_json(paths.policy_path, policy)
    paths.policy_report_path.parent.mkdir(parents=True, exist_ok=True)
    paths.policy_report_path.write_text(render_algorithm_policy_markdown(policy), encoding="utf-8")
    return policy


def _print_policy(policy: Mapping[str, Any], paths: AlgorithmPolicyPaths) -> None:
    summary = _as_dict(policy.get("summary"))
    jobs = _as_dict(policy.get("jobs"))
    print("TRACE-Net algorithm policy")
    print(f"  Status: {policy.get('status')}")
    print(f"  Output dir: {paths.community_dir}")
    print("  Summary:")
    for key in (
        "policy_source_trace_algorithm",
        "policy_repair_batching_algorithm",
        "policy_retrieval_expansion_algorithm",
        "leiden_available",
        "best_repair_batching_score",
        "best_retrieval_expansion_score",
        "leiden_vs_route_repair_delta",
        "leiden_vs_route_retrieval_delta",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("  Job selections:")
    for name in sorted(jobs):
        job = _as_dict(jobs.get(name))
        print(f"    {name}: {job.get('selected_algorithm')} ({job.get('algorithm_family')})")
    print("Files written:")
    print(f"  policy: {paths.policy_path}")
    print(f"  report_md: {paths.policy_report_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net algorithm policy from community ablation metrics.")
    parser.add_argument("--community-dir", default=str(DEFAULT_COMMUNITY_DIR))
    parser.add_argument("--require-leiden-for-retrieval", action="store_true")
    args = parser.parse_args(argv)

    paths = AlgorithmPolicyPaths(community_dir=Path(args.community_dir))
    policy = build_and_write_algorithm_policy(paths, require_leiden_for_retrieval=args.require_leiden_for_retrieval)
    _print_policy(policy, paths)
    return 0 if policy.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
