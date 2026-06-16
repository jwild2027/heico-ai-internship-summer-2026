"""
TRACE-Net Artifact Dirty Planner v1.

Read-only planner that explains which downstream TRACE-Net artifacts should be
rebuilt when an input artifact or file changes.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_artifact_dirty_planner_v1"
DEFAULT_OUTPUT_NAME = "trace_net_artifact_dirty_planner_v1.json"
DEFAULT_QUALITY_NAME = "trace_net_artifact_dirty_planner_v1_quality.json"
DEFAULT_MARKDOWN_NAME = "trace_net_artifact_dirty_planner_v1.md"

PASS = "PASS"
FAIL = "FAIL"

SAFETY_ZERO_KEYS = [
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "source_truth_mutation_allowed_count",
    "source_truth_mutations_performed",
    "direct_answer_allowed_count",
    "claim_proof_allowed_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "feedback_as_proof_count",
    "community_as_proof_count",
    "category_as_proof_count",
    "retrieval_only_answer_allowed_count",
]

# Advisory TRACE-Net dependency hints. These are used only to make the first
# dirty planner useful even when the registry artifact does not yet know about a
# brand-new module. Registry edges still remain the primary source of truth.
TRACE_NET_DEFAULT_DOWNSTREAM_RULES: dict[str, list[str]] = {
    "opensearch_adapter": [
        "opensearch_loader_smoke",
        "hybrid_retrieval_v2",
        "ask_api_dynamic_retrieval_v2",
    ],
    "opensearch_loader_smoke": [
        "hybrid_retrieval_v2",
    ],
    "hybrid_retrieval_v2": [
        "dynamic_final_gate_execution",
        "retrieval_critic",
        "ask_api_dynamic_retrieval_v2",
        "ask_api_final_return_policy_v21",
    ],
    "dynamic_final_gate_execution": [
        "retrieval_critic",
        "evidence_sufficiency_critic",
        "answer_claim_critic",
        "ask_api_final_return_policy_v21",
    ],
    "retrieval_critic": [
        "evidence_sufficiency_critic",
        "answer_claim_critic",
        "ask_api_final_return_policy_v21",
    ],
    "evidence_sufficiency_critic": [
        "answer_claim_critic",
        "ask_api_final_return_policy_v21",
    ],
    "answer_claim_critic": [
        "ask_api_final_return_policy_v21",
    ],
    "feedback_memory": [
        "hybrid_retrieval_v2",
        "retrieval_critic",
        "human_review_queue",
        "graph_ui_community_overlay",
    ],
    "category_aware_leiden_overlay": [
        "hybrid_retrieval_v2",
        "category_aware_graph_ui_overlay",
    ],
    "leiden_graph_communities": [
        "graph_ui_community_overlay",
        "category_aware_leiden_overlay",
        "dublin_core_crosswalk",
        "feedback_memory",
    ],
    "dublin_core_crosswalk_refined": [
        "dublin_core_source_package_extension",
        "element_category_taxonomy",
        "category_aware_leiden_overlay",
    ],
    "element_category_taxonomy": [
        "category_aware_leiden_overlay",
        "category_aware_graph_ui_overlay",
    ],
    "human_review_triage": [
        "human_review_decisions",
        "human_review_workbench",
        "dublin_core_crosswalk",
    ],
    "human_review_queue": [
        "human_review_triage",
    ],
}


@dataclass(frozen=True)
class PlannerThresholds:
    min_planner_records: int = 1
    min_dirty_artifacts: int = 1
    max_dependency_cycle_count: int = 0
    require_registry_quality_pass: bool = False


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def slug(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    text = text.split("/")[-1]
    if text.endswith(".json"):
        text = text[:-5]
    prefixes = [
        "trace_net_",
        "README_trace_net_",
    ]
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix) :]
    # Canonical artifact IDs usually drop v1 but preserve v2/v21 because those
    # are meaningful active module names, e.g. hybrid_retrieval_v2 and
    # ask_api_final_return_policy_v21.
    suffixes = [
        "_v1_quality",
        "_quality",
        "_v1",
    ]
    for suffix in suffixes:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text.lower().replace("-", "_").replace(" ", "_")


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def get_nested(record: dict[str, Any], path: str) -> Any:
    cur: Any = record
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def normalize_quality_status(payload: dict[str, Any] | None, record: dict[str, Any] | None = None) -> str | None:
    candidates: list[Any] = []
    if record:
        candidates.extend(
            [
                record.get("quality_status"),
                record.get("status"),
                get_nested(record, "summary.quality_status"),
                get_nested(record, "summary.status"),
            ]
        )
    if payload:
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        candidates.extend(
            [
                payload.get("quality_status"),
                payload.get("status"),
                summary.get("quality_status"),
                summary.get("status"),
            ]
        )
    for value in candidates:
        if isinstance(value, str) and value.strip():
            normalized = value.strip().upper()
            if normalized in {"PASS", "OK", "BUILT", "LOADED", "READY"}:
                return PASS
            if normalized in {"FAIL", "FAILED", "ERROR", "BLOCKED"}:
                return FAIL
            return value.strip()
    return None


def find_registry_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    possible_keys = [
        "artifacts",
        "artifact_records",
        "registry_records",
        "records",
        "nodes",
    ]
    for key in possible_keys:
        value = payload.get(key)
        if isinstance(value, list) and any(isinstance(x, dict) for x in value):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            rows: list[dict[str, Any]] = []
            for k, v in value.items():
                if isinstance(v, dict):
                    row = dict(v)
                    row.setdefault("artifact_id", k)
                    rows.append(row)
            if rows:
                return rows
    return []


def artifact_id_from_record(record: dict[str, Any]) -> str:
    raw = first_non_empty(
        record.get("artifact_id"),
        record.get("id"),
        record.get("name"),
        record.get("module_name"),
        record.get("module"),
        record.get("artifact_name"),
        record.get("output_dir"),
        record.get("artifact_path"),
        record.get("path"),
        record.get("report_path"),
    )
    return slug(raw)


def record_paths(record: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in [
        "path",
        "artifact_path",
        "report_path",
        "quality_path",
        "output_dir",
        "directory",
        "readme_path",
    ]:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(value.replace("\\", "/"))
    for key in ["paths", "source_paths", "input_paths", "output_paths", "files"]:
        value = record.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    paths.append(item.replace("\\", "/"))
    return sorted(set(paths))


def normalize_artifacts(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for record in find_registry_records(payload):
        artifact_id = artifact_id_from_record(record)
        if not artifact_id:
            continue
        artifacts[artifact_id] = {
            "artifact_id": artifact_id,
            "display_name": first_non_empty(record.get("display_name"), record.get("name"), record.get("artifact_name"), artifact_id),
            "quality_status": normalize_quality_status(None, record),
            "known_in_registry": True,
            "paths": record_paths(record),
            "raw_record_keys": sorted(record.keys()),
        }
    return artifacts


def edge_endpoint(edge: dict[str, Any], names: Iterable[str]) -> str:
    for name in names:
        value = edge.get(name)
        if isinstance(value, str) and value.strip():
            return slug(value)
    return ""


def find_edge_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    possible_keys = [
        "dependency_edges",
        "artifact_dependency_edges",
        "dependency_records",
        "edges",
        "links",
    ]
    for key in possible_keys:
        value = payload.get(key)
        if isinstance(value, list) and any(isinstance(x, dict) for x in value):
            return [x for x in value if isinstance(x, dict)]
    return []


def normalize_edges(payload: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for edge in find_edge_records(payload):
        upstream = edge_endpoint(
            edge,
            [
                "upstream_artifact_id",
                "source_artifact_id",
                "source_id",
                "source",
                "from_artifact_id",
                "from",
                "dependency_artifact_id",
                "dependency",
                "depends_on",
                "input_artifact_id",
            ],
        )
        downstream = edge_endpoint(
            edge,
            [
                "downstream_artifact_id",
                "target_artifact_id",
                "target_id",
                "target",
                "to_artifact_id",
                "to",
                "dependent_artifact_id",
                "dependent",
                "artifact_id",
                "output_artifact_id",
            ],
        )
        if upstream and downstream and upstream != downstream:
            normalized.append(
                {
                    "upstream_artifact_id": upstream,
                    "downstream_artifact_id": downstream,
                    "edge_source": "artifact_dependency_registry",
                    "raw_edge_keys": sorted(edge.keys()),
                }
            )
    return normalized


def add_default_trace_net_edges(
    artifacts: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = {(e["upstream_artifact_id"], e["downstream_artifact_id"]) for e in edges}
    out = list(edges)
    for upstream, downstreams in TRACE_NET_DEFAULT_DOWNSTREAM_RULES.items():
        if upstream not in artifacts:
            artifacts.setdefault(
                upstream,
                {
                    "artifact_id": upstream,
                    "display_name": upstream,
                    "quality_status": None,
                    "known_in_registry": False,
                    "paths": [],
                    "raw_record_keys": [],
                },
            )
        for downstream in downstreams:
            artifacts.setdefault(
                downstream,
                {
                    "artifact_id": downstream,
                    "display_name": downstream,
                    "quality_status": None,
                    "known_in_registry": False,
                    "paths": [],
                    "raw_record_keys": [],
                },
            )
            pair = (upstream, downstream)
            if pair not in existing:
                out.append(
                    {
                        "upstream_artifact_id": upstream,
                        "downstream_artifact_id": downstream,
                        "edge_source": "trace_net_default_rule",
                        "raw_edge_keys": [],
                    }
                )
                existing.add(pair)
    return out


def match_changed_inputs_to_artifacts(changed_inputs: list[str], artifacts: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = defaultdict(list)
    for raw in changed_inputs:
        normalized_input = raw.replace("\\", "/").lower()
        input_slug = slug(raw)
        for artifact_id, record in artifacts.items():
            if input_slug and (input_slug == artifact_id or input_slug in artifact_id or artifact_id in input_slug):
                matches[artifact_id].append(raw)
                continue
            for path in record.get("paths", []):
                p = str(path).lower().replace("\\", "/")
                if p and (p in normalized_input or normalized_input in p):
                    matches[artifact_id].append(raw)
                    break
    return {k: sorted(set(v)) for k, v in matches.items()}


def detect_cycles(artifact_ids: list[str], edges: list[dict[str, Any]]) -> list[list[str]]:
    graph: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        graph[edge["upstream_artifact_id"]].append(edge["downstream_artifact_id"])

    state: dict[str, int] = {}
    stack: list[str] = []
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if state.get(nxt) == 1:
                try:
                    idx = stack.index(nxt)
                except ValueError:
                    idx = 0
                cycles.append(stack[idx:] + [nxt])
            elif state.get(nxt, 0) == 0:
                dfs(nxt)
        stack.pop()
        state[node] = 2

    for artifact_id in sorted(set(artifact_ids) | set(graph.keys())):
        if state.get(artifact_id, 0) == 0:
            dfs(artifact_id)
    # Dedupe cycles by normalized tuple.
    deduped: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for cycle in cycles:
        key = tuple(cycle)
        if key not in seen:
            seen.add(key)
            deduped.append(cycle)
    return deduped


def downstream_closure(
    seed_artifacts: list[str],
    edges: list[dict[str, Any]],
) -> tuple[dict[str, int], dict[str, set[str]], dict[str, list[str]]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    incoming_reason_edges: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        upstream = edge["upstream_artifact_id"]
        downstream = edge["downstream_artifact_id"]
        adjacency[upstream].append(downstream)
        incoming_reason_edges[downstream].append(upstream)

    depths: dict[str, int] = {}
    upstream_sources: dict[str, set[str]] = defaultdict(set)
    q: deque[tuple[str, int, str]] = deque()
    for seed in sorted(set(seed_artifacts)):
        q.append((seed, 0, seed))

    while q:
        current, depth, root = q.popleft()
        for downstream in sorted(adjacency.get(current, [])):
            next_depth = depth + 1
            if downstream not in depths or next_depth < depths[downstream]:
                depths[downstream] = next_depth
            before = set(upstream_sources[downstream])
            upstream_sources[downstream].add(root)
            if upstream_sources[downstream] != before or next_depth <= depths.get(downstream, next_depth):
                q.append((downstream, next_depth, root))

    return depths, upstream_sources, incoming_reason_edges


def quality_from_summary(summary: dict[str, Any], thresholds: PlannerThresholds) -> tuple[str, list[str]]:
    failures: list[str] = []
    if summary.get("planner_record_count", 0) < thresholds.min_planner_records:
        failures.append(
            f"planner_record_count {summary.get('planner_record_count', 0)} < {thresholds.min_planner_records}"
        )
    if summary.get("dirty_artifact_count", 0) < thresholds.min_dirty_artifacts:
        failures.append(
            f"dirty_artifact_count {summary.get('dirty_artifact_count', 0)} < {thresholds.min_dirty_artifacts}"
        )
    if summary.get("dependency_cycle_count", 0) > thresholds.max_dependency_cycle_count:
        failures.append(
            f"dependency_cycle_count {summary.get('dependency_cycle_count', 0)} > {thresholds.max_dependency_cycle_count}"
        )
    if thresholds.require_registry_quality_pass and summary.get("source_registry_quality_status") != PASS:
        failures.append("source_registry_quality_status is not PASS")
    for key in SAFETY_ZERO_KEYS:
        if summary.get(key, 0) != 0:
            failures.append(f"{key} must be 0")
    return (PASS if not failures else FAIL), failures


def build_dirty_planner(
    artifact_registry: str | Path,
    changed_artifacts: list[str] | None = None,
    changed_inputs: list[str] | None = None,
    output_dir: str | Path | None = None,
    thresholds: PlannerThresholds | None = None,
    include_default_trace_net_rules: bool = True,
    write_quality: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or PlannerThresholds()
    changed_artifacts = [slug(x) for x in (changed_artifacts or []) if slug(x)]
    changed_inputs = [x for x in (changed_inputs or []) if str(x).strip()]

    registry_payload = load_json(artifact_registry)
    source_registry_quality_status = normalize_quality_status(registry_payload)
    artifacts = normalize_artifacts(registry_payload)
    edges = normalize_edges(registry_payload)

    if include_default_trace_net_rules:
        edges = add_default_trace_net_edges(artifacts, edges)

    for artifact_id in changed_artifacts:
        artifacts.setdefault(
            artifact_id,
            {
                "artifact_id": artifact_id,
                "display_name": artifact_id,
                "quality_status": None,
                "known_in_registry": False,
                "paths": [],
                "raw_record_keys": [],
            },
        )

    changed_input_matches = match_changed_inputs_to_artifacts(changed_inputs, artifacts)
    seed_artifacts = sorted(set(changed_artifacts) | set(changed_input_matches.keys()))

    cycles = detect_cycles(list(artifacts.keys()), edges)
    depths, upstream_sources, incoming_reason_edges = downstream_closure(seed_artifacts, edges)

    dirty_artifact_ids = sorted(depths.keys(), key=lambda x: (depths[x], x))
    planner_records: list[dict[str, Any]] = []
    for order, artifact_id in enumerate(dirty_artifact_ids, 1):
        record = artifacts.get(
            artifact_id,
            {
                "artifact_id": artifact_id,
                "display_name": artifact_id,
                "quality_status": None,
                "known_in_registry": False,
                "paths": [],
                "raw_record_keys": [],
            },
        )
        direct_upstreams = sorted(set(incoming_reason_edges.get(artifact_id, [])) & (set(seed_artifacts) | set(dirty_artifact_ids)))
        planner_records.append(
            {
                "planner_record_id": f"{SCHEMA_VERSION}:rebuild:{order:04d}:{artifact_id}",
                "artifact_id": artifact_id,
                "display_name": record.get("display_name") or artifact_id,
                "rebuild_order": order,
                "dependency_depth": depths[artifact_id],
                "dirty_reason": "downstream_of_changed_artifact_or_input",
                "seed_artifacts": sorted(upstream_sources.get(artifact_id, [])),
                "direct_dirty_upstreams": direct_upstreams,
                "known_in_registry": bool(record.get("known_in_registry")),
                "registry_quality_status": record.get("quality_status"),
                "paths": record.get("paths", []),
                "recommended_action": "rebuild_and_quality_check_before_using_downstream",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
            }
        )

    edge_source_counts = Counter(edge.get("edge_source") for edge in edges)
    quality_status_counts = Counter(
        record.get("registry_quality_status") or "unknown" for record in planner_records
    )

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "trace_net_read_only_artifact_dirty_planner_v1",
        "source_registry_path": str(artifact_registry),
        "source_registry_quality_status": source_registry_quality_status,
        "changed_artifact_count": len(changed_artifacts),
        "changed_input_count": len(changed_inputs),
        "seed_artifact_count": len(seed_artifacts),
        "artifact_record_count": len(artifacts),
        "dependency_edge_count": len(edges),
        "default_rule_edge_count": edge_source_counts.get("trace_net_default_rule", 0),
        "registry_edge_count": edge_source_counts.get("artifact_dependency_registry", 0),
        "dependency_cycle_count": len(cycles),
        "dirty_artifact_count": len(dirty_artifact_ids),
        "planner_record_count": len(planner_records),
        "unknown_seed_artifact_count": sum(1 for x in seed_artifacts if not artifacts.get(x, {}).get("known_in_registry")),
        "planner_quality_status_counts": dict(sorted(quality_status_counts.items())),
    }
    for key in SAFETY_ZERO_KEYS:
        summary[key] = 0

    quality_status, failures = quality_from_summary(summary, thresholds)
    status = "DIRTY_PLAN_BUILT" if quality_status == PASS else "DIRTY_PLAN_NEEDS_REVIEW"

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "quality_status": quality_status,
        "quality_failures": failures,
        "summary": summary,
        "changed_artifacts": changed_artifacts,
        "changed_inputs": changed_inputs,
        "changed_input_matches": changed_input_matches,
        "seed_artifacts": seed_artifacts,
        "dependency_cycles": cycles,
        "dirty_artifacts": dirty_artifact_ids,
        "planner_records": planner_records,
        "dependency_edges_used": edges,
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "source_truth_mutation": False,
            "answer_permission": False,
            "claim_proof_authority": False,
        },
    }

    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        report_path = output / DEFAULT_OUTPUT_NAME
        write_json(report_path, report)
        if write_quality:
            quality_payload = build_quality_payload(report, thresholds)
            write_json(output / DEFAULT_QUALITY_NAME, quality_payload)
        write_markdown(output / DEFAULT_MARKDOWN_NAME, report)
        report["report_path"] = str(report_path)
        if write_quality:
            report["quality_path"] = str(output / DEFAULT_QUALITY_NAME)
    return report


def build_quality_payload(report: dict[str, Any], thresholds: PlannerThresholds) -> dict[str, Any]:
    summary = dict(report.get("summary") or {})
    quality_status, failures = quality_from_summary(summary, thresholds)
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": quality_status,
        "quality_status": quality_status,
        "quality_failures": failures,
        "summary": summary,
        "thresholds": {
            "min_planner_records": thresholds.min_planner_records,
            "min_dirty_artifacts": thresholds.min_dirty_artifacts,
            "max_dependency_cycle_count": thresholds.max_dependency_cycle_count,
            "require_registry_quality_pass": thresholds.require_registry_quality_pass,
        },
    }


def check_dirty_planner_quality(
    report_path: str | Path,
    thresholds: PlannerThresholds | None = None,
    write_json_report: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or PlannerThresholds()
    report = load_json(report_path)
    quality_payload = build_quality_payload(report, thresholds)
    if write_json_report:
        p = Path(report_path)
        write_json(p.with_name(DEFAULT_QUALITY_NAME), quality_payload)
    return quality_payload


def write_markdown(path: str | Path, report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    lines = [
        "# TRACE-Net Artifact Dirty Planner v1",
        "",
        f"Quality status: `{report.get('quality_status')}`",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "source_registry_quality_status",
        "seed_artifact_count",
        "dirty_artifact_count",
        "planner_record_count",
        "dependency_edge_count",
        "dependency_cycle_count",
        "default_rule_edge_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- `{key}`: `{summary.get(key)}`")
    lines.extend(["", "## Dirty artifacts", ""])
    for record in report.get("planner_records", [])[:50]:
        lines.append(
            f"- {record.get('rebuild_order')}. `{record.get('artifact_id')}` "
            f"depth={record.get('dependency_depth')} seeds={record.get('seed_artifacts')}"
        )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_build_summary(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    print("TRACE-Net Artifact Dirty Planner v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "source_registry_quality_status",
        "changed_artifact_count",
        "changed_input_count",
        "seed_artifact_count",
        "artifact_record_count",
        "dependency_edge_count",
        "default_rule_edge_count",
        "dependency_cycle_count",
        "dirty_artifact_count",
        "planner_record_count",
        "unknown_seed_artifact_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if report.get("report_path"):
        print(f" report_path: {report['report_path']}")
    if report.get("quality_path"):
        print(f" quality_path: {report['quality_path']}")


def print_quality_summary(payload: dict[str, Any]) -> None:
    summary = payload.get("summary", {})
    print("TRACE-Net Artifact Dirty Planner v1 quality")
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {payload.get('quality_status')}")
    for key in [
        "source_registry_quality_status",
        "seed_artifact_count",
        "dirty_artifact_count",
        "planner_record_count",
        "dependency_cycle_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if payload.get("quality_failures"):
        print(" quality_failures:")
        for failure in payload["quality_failures"]:
            print(f"  - {failure}")


def read_changed_input_file(path: str | None) -> list[str]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing changed-input file: {p}")
    return [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Artifact Dirty Planner v1.")
    parser.add_argument("--artifact-registry", required=True)
    parser.add_argument("--changed-artifact", action="append", default=[])
    parser.add_argument("--changed-input", action="append", default=[])
    parser.add_argument("--changed-input-file")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-planner-records", type=int, default=1)
    parser.add_argument("--min-dirty-artifacts", type=int, default=1)
    parser.add_argument("--max-dependency-cycles", type=int, default=0)
    parser.add_argument("--require-registry-quality-pass", action="store_true")
    parser.add_argument("--no-default-trace-net-rules", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    changed_inputs = list(args.changed_input) + read_changed_input_file(args.changed_input_file)
    thresholds = PlannerThresholds(
        min_planner_records=args.min_planner_records,
        min_dirty_artifacts=args.min_dirty_artifacts,
        max_dependency_cycle_count=args.max_dependency_cycles,
        require_registry_quality_pass=args.require_registry_quality_pass,
    )
    report = build_dirty_planner(
        artifact_registry=args.artifact_registry,
        changed_artifacts=args.changed_artifact,
        changed_inputs=changed_inputs,
        output_dir=args.output_dir,
        thresholds=thresholds,
        include_default_trace_net_rules=not args.no_default_trace_net_rules,
        write_quality=args.quality,
    )
    print_build_summary(report)
    return 0 if report.get("quality_status") == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
