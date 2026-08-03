from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from tiff.trace_net_feedback import FeedbackPaths, TRACE_NET_DIR, _read_json, _read_jsonl, _write_json


@dataclass(frozen=True)
class FeedbackQualityPaths:
    trace_net_dir: Path = TRACE_NET_DIR
    feedback_dir: Path = TRACE_NET_DIR / "feedback"
    quality_path: Path = TRACE_NET_DIR / "feedback" / "feedback_quality.json"

    @property
    def summary(self) -> Path:
        return self.feedback_dir / "feedback_summary.json"

    @property
    def events(self) -> Path:
        return self.feedback_dir / "feedback_events.jsonl"

    @property
    def graph_nodes(self) -> Path:
        return self.feedback_dir / "feedback_graph_nodes.json"

    @property
    def graph_edges(self) -> Path:
        return self.feedback_dir / "feedback_graph_edges.json"

    @property
    def policy_signals(self) -> Path:
        return self.feedback_dir / "feedback_policy_signals.jsonl"


def check_feedback_quality(
    paths: FeedbackQualityPaths,
    *,
    min_events: int = 0,
    min_policy_signals: int = 0,
    max_source_truth_mutations: int = 0,
    max_unlinked_ask_events: Optional[int] = None,
    max_context_warning_events: Optional[int] = None,
    min_policy_signal_eligible_events: int = 0,
    require_advisory_only: bool = True,
) -> Dict[str, Any]:
    summary = _read_json(paths.summary, {}) or {}
    events = _read_jsonl(paths.events)
    signals = _read_jsonl(paths.policy_signals)
    nodes = _read_json(paths.graph_nodes, []) or []
    edges = _read_json(paths.graph_edges, []) or []

    event_count = len(events)
    advisory_events_scan = sum(1 for e in events if e.get("advisory_only") is True)
    mutation_scan = sum(1 for e in events if e.get("source_truth_mutation") or e.get("ranking_mutation"))
    ask_linked_scan = sum(1 for e in events if e.get("ask_run_id"))
    answer_linked_scan = sum(1 for e in events if e.get("answer_id"))
    context_valid_scan = sum(1 for e in events if e.get("context_status") == "valid")
    context_warning_scan = event_count - context_valid_scan
    policy_signal_eligible_scan = sum(1 for e in events if e.get("policy_signal_eligible") is True)
    query_mismatch_scan = sum(1 for e in events if (e.get("context_validation") or {}).get("query_fingerprint_matches_latest") is False)
    affected_not_in_answer_scan = sum(1 for e in events if (e.get("context_validation") or {}).get("affected_pages_not_in_answer"))
    expected_not_in_answer_scan = sum(1 for e in events if (e.get("context_validation") or {}).get("expected_pages_not_in_answer"))
    unlinked_ask_events = event_count - ask_linked_scan
    signal_count = len(signals)

    checks: List[Dict[str, Any]] = []

    def add_check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add_check("artifacts_present", paths.summary.exists() and paths.events.exists(), f"summary={paths.summary.exists()}; events={paths.events.exists()}")
    add_check("status_ok", summary.get("status") == "OK", f"status={summary.get('status')}")
    add_check("feedback_events", event_count >= min_events, f"events={event_count}; minimum={min_events}")
    add_check("event_count_match", summary.get("feedback_events") in (None, event_count), f"summary={summary.get('feedback_events')}; jsonl={event_count}")
    add_check("advisory_only", (not require_advisory_only) or advisory_events_scan == event_count, f"advisory={advisory_events_scan}; events={event_count}; require={require_advisory_only}")
    add_check("no_source_truth_mutations", mutation_scan <= max_source_truth_mutations, f"mutations={mutation_scan}; max={max_source_truth_mutations}")
    if max_unlinked_ask_events is not None:
        add_check("ask_linked_events", unlinked_ask_events <= max_unlinked_ask_events, f"unlinked_ask_events={unlinked_ask_events}; max={max_unlinked_ask_events}")
    if max_context_warning_events is not None:
        add_check("context_warning_events", context_warning_scan <= max_context_warning_events, f"context_warning_events={context_warning_scan}; max={max_context_warning_events}")
    add_check("policy_signal_eligible_events", policy_signal_eligible_scan >= min_policy_signal_eligible_events, f"eligible={policy_signal_eligible_scan}; minimum={min_policy_signal_eligible_events}")
    add_check("policy_signals", signal_count >= min_policy_signals, f"signals={signal_count}; minimum={min_policy_signals}")
    add_check("graph_nodes", len(nodes) == summary.get("graph_nodes", len(nodes)), f"nodes={len(nodes)}; summary={summary.get('graph_nodes')}")
    add_check("graph_edges", len(edges) == summary.get("graph_edges", len(edges)), f"edges={len(edges)}; summary={summary.get('graph_edges')}")

    status = "OK" if all(c["ok"] for c in checks) else "FAIL"
    result = {
        "status": status,
        "version": "trace_net_feedback_quality_v1_1",
        "feedback_summary_present": paths.summary.exists(),
        "feedback_events_present": paths.events.exists(),
        "feedback_status": summary.get("status"),
        "feedback_events": event_count,
        "feedback_summary_events": summary.get("feedback_events"),
        "feedback_policy_signals": signal_count,
        "feedback_thumb_up_events": summary.get("thumbs_up_events", 0),
        "feedback_thumb_down_events": summary.get("thumbs_down_events", 0),
        "feedback_neutral_events": summary.get("neutral_events", 0),
        "feedback_advisory_only_events": advisory_events_scan,
        "feedback_source_truth_mutation_records": mutation_scan,
        "feedback_ask_linked_event_records": ask_linked_scan,
        "feedback_answer_linked_event_records": answer_linked_scan,
        "feedback_context_valid_events": context_valid_scan,
        "feedback_context_warning_events": context_warning_scan,
        "feedback_policy_signal_eligible_events": policy_signal_eligible_scan,
        "feedback_query_mismatch_events": query_mismatch_scan,
        "feedback_affected_page_not_in_answer_events": affected_not_in_answer_scan,
        "feedback_expected_page_not_in_answer_events": expected_not_in_answer_scan,
        "feedback_unlinked_ask_events": unlinked_ask_events,
        "feedback_graph_nodes": len(nodes),
        "feedback_graph_edges": len(edges),
        "feedback_require_advisory_only": require_advisory_only,
        "checks": checks,
        "summary_path": str(paths.summary),
        "events_path": str(paths.events),
        "policy_signals_path": str(paths.policy_signals),
    }
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quality gate for TRACE-Net feedback graph overlay.")
    parser.add_argument("--trace-net-dir", default=str(TRACE_NET_DIR))
    parser.add_argument("--feedback-dir", default="")
    parser.add_argument("--quality", default="")
    parser.add_argument("--min-events", type=int, default=0)
    parser.add_argument("--min-policy-signals", type=int, default=0)
    parser.add_argument("--max-source-truth-mutations", type=int, default=0)
    parser.add_argument("--max-unlinked-ask-events", type=int, default=None)
    parser.add_argument("--max-context-warning-events", type=int, default=None)
    parser.add_argument("--min-policy-signal-eligible-events", type=int, default=0)
    parser.add_argument("--no-require-advisory-only", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def _make_paths(args: argparse.Namespace) -> FeedbackQualityPaths:
    trace_net_dir = Path(args.trace_net_dir)
    feedback_dir = Path(args.feedback_dir) if args.feedback_dir else trace_net_dir / "feedback"
    quality_path = Path(args.quality) if args.quality else feedback_dir / "feedback_quality.json"
    return FeedbackQualityPaths(trace_net_dir=trace_net_dir, feedback_dir=feedback_dir, quality_path=quality_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    paths = _make_paths(args)
    result = check_feedback_quality(
        paths,
        min_events=args.min_events,
        min_policy_signals=args.min_policy_signals,
        max_source_truth_mutations=args.max_source_truth_mutations,
        max_unlinked_ask_events=args.max_unlinked_ask_events,
        max_context_warning_events=args.max_context_warning_events,
        min_policy_signal_eligible_events=args.min_policy_signal_eligible_events,
        require_advisory_only=not args.no_require_advisory_only,
    )
    if args.write_json:
        _write_json(paths.quality_path, result)
    print("TRACE-Net feedback quality gate")
    print(f"  Status: {result['status']}")
    print("  Summary:")
    for key in [
        "feedback_events",
        "feedback_policy_signals",
        "feedback_thumb_up_events",
        "feedback_thumb_down_events",
        "feedback_advisory_only_events",
        "feedback_source_truth_mutation_records",
        "feedback_ask_linked_event_records",
        "feedback_context_valid_events",
        "feedback_context_warning_events",
        "feedback_policy_signal_eligible_events",
        "feedback_query_mismatch_events",
        "feedback_affected_page_not_in_answer_events",
        "feedback_graph_nodes",
        "feedback_graph_edges",
    ]:
        print(f"    {key}: {result.get(key)}")
    print("  Checks:")
    for check in result["checks"]:
        label = "OK" if check["ok"] else "FAIL"
        print(f"    {label} {check['name']}: {check['detail']}")
    if args.write_json:
        print(f"\nJSON: {paths.quality_path}")
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
