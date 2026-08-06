"""Quality gate for TRACE-Net algorithm policy artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

DEFAULT_COMMUNITY_DIR = Path("local_data/organization/communities")


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


def _check(ok: bool, name: str, detail: str) -> dict[str, Any]:
    return {"status": "OK" if ok else "FAIL", "name": name, "detail": detail}


def _job(policy: Mapping[str, Any], name: str) -> dict[str, Any]:
    return _as_dict(_as_dict(policy.get("jobs")).get(name))


def build_algorithm_policy_quality(
    policy_path: Path,
    *,
    require_route_for_repair: bool = True,
    require_leiden_for_retrieval: bool = True,
    require_deterministic_source_trace: bool = True,
) -> dict[str, Any]:
    policy = _as_dict(_read_json(policy_path, default={}))
    summary = _as_dict(policy.get("summary"))
    jobs = _as_dict(policy.get("jobs"))

    source_trace = _job(policy, "source_trace")
    part_lookup = _job(policy, "exact_part_lookup")
    page_lookup = _job(policy, "exact_page_lookup")
    repair = _job(policy, "trace_net_repair_batching")
    table_batching = _job(policy, "table_extraction_batching")
    retrieval = _job(policy, "broad_retrieval_expansion")
    community_summaries = _job(policy, "community_summaries")

    checks: list[dict[str, Any]] = []
    checks.append(_check(bool(policy), "algorithm_policy_present", f"Policy present at {policy_path}: {bool(policy)}."))
    checks.append(_check(policy.get("status") == "OK", "algorithm_policy_status", f"Policy status is {policy.get('status')}."))
    checks.append(_check(len(jobs) >= 5, "algorithm_policy_jobs", f"job count={len(jobs)}; minimum=5."))
    checks.append(_check(bool(source_trace), "algorithm_policy_source_trace_job", "source_trace job is present."))
    checks.append(_check(bool(repair), "algorithm_policy_repair_job", "trace_net_repair_batching job is present."))
    checks.append(_check(bool(retrieval), "algorithm_policy_retrieval_job", "broad_retrieval_expansion job is present."))
    checks.append(_check(bool(table_batching), "algorithm_policy_table_batching_job", "table_extraction_batching job is present."))
    checks.append(_check(bool(community_summaries), "algorithm_policy_community_summary_job", "community_summaries job is present."))

    if require_deterministic_source_trace:
        deterministic_jobs = {
            "source_trace": source_trace,
            "exact_part_lookup": part_lookup,
            "exact_page_lookup": page_lookup,
        }
        bad = [name for name, job in deterministic_jobs.items() if job.get("selected_algorithm") != "deterministic_graph_traversal"]
        checks.append(_check(not bad, "algorithm_policy_deterministic_source_trace", f"deterministic source-trace jobs with wrong algorithm={bad}."))
    else:
        checks.append(_check(True, "algorithm_policy_deterministic_source_trace", "not required."))

    if require_route_for_repair:
        ok = repair.get("selected_algorithm") == "route_grouping"
        checks.append(_check(ok, "algorithm_policy_route_repair", f"repair selected={repair.get('selected_algorithm')}; expected route_grouping."))
        ok_table = table_batching.get("selected_algorithm") == "route_grouping"
        checks.append(_check(ok_table, "algorithm_policy_route_table_batching", f"table selected={table_batching.get('selected_algorithm')}; expected route_grouping."))
    else:
        checks.append(_check(True, "algorithm_policy_route_repair", "not required."))
        checks.append(_check(True, "algorithm_policy_route_table_batching", "not required."))

    if require_leiden_for_retrieval:
        ok = retrieval.get("selected_algorithm") == "leiden"
        checks.append(_check(ok, "algorithm_policy_leiden_retrieval", f"retrieval selected={retrieval.get('selected_algorithm')}; expected leiden."))
        ok_summary = community_summaries.get("selected_algorithm") == "leiden"
        checks.append(_check(ok_summary, "algorithm_policy_leiden_community_summaries", f"community summaries selected={community_summaries.get('selected_algorithm')}; expected leiden."))
    else:
        checks.append(_check(True, "algorithm_policy_leiden_retrieval", "not required."))
        checks.append(_check(True, "algorithm_policy_leiden_community_summaries", "not required."))

    # Guard against accidental community use as source truth.
    source_uses_communities = bool(source_trace.get("uses_communities")) or bool(part_lookup.get("uses_communities")) or bool(page_lookup.get("uses_communities"))
    checks.append(_check(not source_uses_communities, "algorithm_policy_no_communities_for_truth", f"source/page/part community use={source_uses_communities}."))

    summary_out = {
        "algorithm_policy_present": bool(policy),
        "algorithm_policy_status": policy.get("status"),
        "algorithm_policy_version": policy.get("policy_version"),
        "algorithm_policy_path": str(policy_path),
        "algorithm_policy_jobs": len(jobs),
        "algorithm_policy_source_trace_algorithm": source_trace.get("selected_algorithm"),
        "algorithm_policy_part_lookup_algorithm": part_lookup.get("selected_algorithm"),
        "algorithm_policy_page_lookup_algorithm": page_lookup.get("selected_algorithm"),
        "algorithm_policy_repair_batching_algorithm": repair.get("selected_algorithm"),
        "algorithm_policy_table_batching_algorithm": table_batching.get("selected_algorithm"),
        "algorithm_policy_retrieval_expansion_algorithm": retrieval.get("selected_algorithm"),
        "algorithm_policy_community_summaries_algorithm": community_summaries.get("selected_algorithm"),
        "algorithm_policy_best_repair_score": summary.get("best_repair_batching_score"),
        "algorithm_policy_best_retrieval_score": summary.get("best_retrieval_expansion_score"),
        "algorithm_policy_leiden_available": summary.get("leiden_available"),
        "algorithm_policy_require_route_for_repair": require_route_for_repair,
        "algorithm_policy_require_leiden_for_retrieval": require_leiden_for_retrieval,
        "algorithm_policy_require_deterministic_source_trace": require_deterministic_source_trace,
    }

    status = "OK" if all(c["status"] == "OK" for c in checks) else "FAIL"
    return {"status": status, "summary": summary_out, "checks": checks}


def print_quality_report(report: Mapping[str, Any]) -> None:
    print("TRACE-Net algorithm policy quality gate")
    print(f"  Status: {report.get('status')}")
    print("  Summary:")
    for key, value in _as_dict(report.get("summary")).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in report.get("checks", []):
        if isinstance(check, dict):
            print(f"    {check.get('status')} {check.get('name')}: {check.get('detail')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net algorithm policy quality.")
    parser.add_argument("--community-dir", default=str(DEFAULT_COMMUNITY_DIR))
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--allow-non-route-repair", action="store_true")
    parser.add_argument("--allow-non-leiden-retrieval", action="store_true")
    parser.add_argument("--allow-non-deterministic-source-trace", action="store_true")
    args = parser.parse_args(argv)

    community_dir = Path(args.community_dir)
    policy_path = community_dir / "community_algorithm_policy.json"
    quality_path = community_dir / "community_algorithm_policy_quality.json"
    report = build_algorithm_policy_quality(
        policy_path,
        require_route_for_repair=not args.allow_non_route_repair,
        require_leiden_for_retrieval=not args.allow_non_leiden_retrieval,
        require_deterministic_source_trace=not args.allow_non_deterministic_source_trace,
    )
    print_quality_report(report)
    if args.write_json:
        _write_json(quality_path, report)
        print(f"\nJSON: {quality_path}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
