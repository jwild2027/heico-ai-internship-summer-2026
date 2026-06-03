"""Quality gate for TRACE-Net weights policy v1."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .trace_net_weights_policy import (
    REQUIRED_GLOBAL_SAFETY_GATES,
    REQUIRED_LAYERS,
    WEIGHTS_POLICY_VERSION,
    validate_weight_policy,
)

DEFAULT_DIR = Path("local_data/organization/trace_net/weights")
DEFAULT_POLICY = DEFAULT_DIR / "trace_net_weights_policy.json"
DEFAULT_SUMMARY = DEFAULT_DIR / "trace_net_weights_policy_summary.json"
DEFAULT_NODES = DEFAULT_DIR / "trace_net_weights_policy_graph_nodes.json"
DEFAULT_EDGES = DEFAULT_DIR / "trace_net_weights_policy_graph_edges.json"
DEFAULT_QUALITY = DEFAULT_DIR / "trace_net_weights_policy_quality.json"


@dataclass(frozen=True)
class QualityOptions:
    policy_path: Path = DEFAULT_POLICY
    summary_path: Path = DEFAULT_SUMMARY
    graph_nodes_path: Path = DEFAULT_NODES
    graph_edges_path: Path = DEFAULT_EDGES
    quality_path: Path = DEFAULT_QUALITY
    min_layers: int = 7
    require_source_text_policy: bool = True
    require_feedback_weights: bool = True
    require_retrieval_weights: bool = True
    max_validation_errors: int = 0
    require_no_production_ranking_change: bool = True
    write_json: bool = False


def _repo_relative(path: Path) -> str:
    return str(path).replace("/", os.sep)


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _json_len(path: Path) -> int:
    value = _load_json(path)
    if isinstance(value, list):
        return len(value)
    return 0


def check_trace_net_weights_policy_quality(options: QualityOptions) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    failures: List[str] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "status": "OK" if ok else "FAIL", "detail": detail})
        if not ok:
            failures.append(f"{name}: {detail}")

    policy = _load_json(options.policy_path)
    summary = _load_json(options.summary_path)
    policy_present = isinstance(policy, dict)
    summary_present = isinstance(summary, dict)
    add("artifacts_present", policy_present and summary_present, f"policy={policy_present}; summary={summary_present}")

    if not policy_present:
        policy = {}
    if not summary_present:
        summary = {}

    status = policy.get("status") or summary.get("status")
    add("status_ok", status == "OK", f"status={status!r}")

    version = policy.get("version") or summary.get("version")
    add("version", version == WEIGHTS_POLICY_VERSION, f"version={version!r}")

    validation_checks, validation_errors, metrics = validate_weight_policy(policy) if policy else ([], ["missing policy"], {})
    validation_error_count = len(validation_errors)
    add("validation_errors", validation_error_count <= options.max_validation_errors, f"errors={validation_error_count}; max={options.max_validation_errors}")

    layers = ((policy.get("confidence") or {}).get("layers") or {}) if isinstance(policy, dict) else {}
    layer_count = len(layers)
    add("layer_count", layer_count >= options.min_layers, f"layers={layer_count}; minimum={options.min_layers}")

    missing_required = [layer for layer in REQUIRED_LAYERS if layer not in layers]
    add("required_layers", not missing_required, f"missing={missing_required}")

    if options.require_source_text_policy:
        source_text = layers.get("source_text_evidence") or {}
        ok = bool(source_text) and source_text.get("default_rag_action") == "include_as_source_text_evidence"
        add("source_text_policy", ok, f"present={bool(source_text)}; rag={source_text.get('default_rag_action')}")

    if options.require_retrieval_weights:
        retrieval = policy.get("retrieval_ranking") or {}
        bucket_bonuses = retrieval.get("bucket_bonuses") or {}
        required_buckets = ["verified_part_evidence", "source_text_evidence", "derived_context", "source_evidence"]
        missing_buckets = [bucket for bucket in required_buckets if bucket not in bucket_bonuses]
        add("retrieval_weights", not missing_buckets, f"missing_buckets={missing_buckets}")

    if options.require_feedback_weights:
        feedback = policy.get("feedback_ranking") or {}
        reason_weights = feedback.get("reason_weights") or {}
        ok = reason_weights.get("wrong_page", 0) < 0 and reason_weights.get("answer_correct", 0) > 0 and feedback.get("cap_min", 0) < 0 < feedback.get("cap_max", 0)
        add("feedback_weights", ok, f"reasons={len(reason_weights)}; cap={feedback.get('cap_min')}..{feedback.get('cap_max')}")
        ok_context = "context_status_valid" in (feedback.get("eligible_only_when") or []) and "context_warning" in (feedback.get("ignore_when") or [])
        add("feedback_context_validation", ok_context, f"eligible={feedback.get('eligible_only_when')}; ignore={feedback.get('ignore_when')}")

    rollout = policy.get("rollout") or {}
    if options.require_no_production_ranking_change:
        ok = rollout.get("production_ranking_changed") is False and rollout.get("source_truth_mutation_allowed") is False
        add("no_production_changes", ok, f"production_ranking_changed={rollout.get('production_ranking_changed')}; source_truth_mutation_allowed={rollout.get('source_truth_mutation_allowed')}")

    gates = policy.get("global_safety_gates") or []
    missing_gates = [gate for gate in REQUIRED_GLOBAL_SAFETY_GATES if gate not in gates]
    add("global_safety_gates", not missing_gates, f"missing={missing_gates}")

    graph_nodes = _json_len(options.graph_nodes_path)
    graph_edges = _json_len(options.graph_edges_path)
    add("graph_nodes", graph_nodes > 0, f"graph_nodes={graph_nodes}")
    add("graph_edges", graph_edges > 0, f"graph_edges={graph_edges}")

    quality = {
        "status": "OK" if not failures else "FAIL",
        "version": WEIGHTS_POLICY_VERSION,
        "policy_present": policy_present,
        "summary_present": summary_present,
        "policy_status": status,
        "policy_version": version,
        "policy_layers": layer_count,
        "validation_error_count": validation_error_count,
        "validation_errors": validation_errors,
        "weight_sums": metrics.get("weight_sums", {}),
        "risk_score_count": metrics.get("risk_score_count", 0),
        "retrieval_bucket_bonus_count": metrics.get("retrieval_bucket_bonus_count", 0),
        "feedback_reason_count": metrics.get("feedback_reason_count", 0),
        "global_safety_gate_count": metrics.get("global_safety_gate_count", 0),
        "production_ranking_changed": rollout.get("production_ranking_changed"),
        "source_truth_mutation_allowed": rollout.get("source_truth_mutation_allowed"),
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "policy_path": _repo_relative(options.policy_path),
        "summary_path": _repo_relative(options.summary_path),
        "checks": checks,
        "failures": failures,
    }
    if options.write_json:
        options.quality_path.parent.mkdir(parents=True, exist_ok=True)
        options.quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return quality


def print_quality(quality: Dict[str, Any]) -> None:
    print("TRACE-Net weights policy quality gate")
    print(f"  Status: {quality.get('status')}")
    print("  Summary:")
    for key in [
        "policy_present",
        "summary_present",
        "policy_status",
        "policy_version",
        "policy_layers",
        "validation_error_count",
        "risk_score_count",
        "retrieval_bucket_bonus_count",
        "feedback_reason_count",
        "global_safety_gate_count",
        "production_ranking_changed",
        "source_truth_mutation_allowed",
        "graph_nodes",
        "graph_edges",
    ]:
        print(f"    {key}: {quality.get(key)}")
    print("  Checks:")
    for check in quality.get("checks", []):
        print(f"    {check['status']} {check['name']}: {check['detail']}")
    qpath = Path("local_data/organization/trace_net/weights/trace_net_weights_policy_quality.json")
    if qpath.exists():
        print(f"\nJSON: {_repo_relative(qpath)}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net weights policy quality.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--graph-nodes", default=str(DEFAULT_NODES))
    parser.add_argument("--graph-edges", default=str(DEFAULT_EDGES))
    parser.add_argument("--quality", default=str(DEFAULT_QUALITY))
    parser.add_argument("--min-layers", type=int, default=7)
    parser.add_argument("--max-validation-errors", type=int, default=0)
    parser.add_argument("--no-source-text-policy", action="store_true")
    parser.add_argument("--no-feedback-weights", action="store_true")
    parser.add_argument("--no-retrieval-weights", action="store_true")
    parser.add_argument("--allow-production-ranking-change", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    options = QualityOptions(
        policy_path=Path(args.policy),
        summary_path=Path(args.summary),
        graph_nodes_path=Path(args.graph_nodes),
        graph_edges_path=Path(args.graph_edges),
        quality_path=Path(args.quality),
        min_layers=args.min_layers,
        max_validation_errors=args.max_validation_errors,
        require_source_text_policy=not args.no_source_text_policy,
        require_feedback_weights=not args.no_feedback_weights,
        require_retrieval_weights=not args.no_retrieval_weights,
        require_no_production_ranking_change=not args.allow_production_ranking_change,
        write_json=bool(args.write_json),
    )
    quality = check_trace_net_weights_policy_quality(options)
    print_quality(quality)
    return 0 if quality.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
