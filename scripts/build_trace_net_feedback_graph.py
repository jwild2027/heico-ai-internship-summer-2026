from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_feedback import FeedbackPaths, TRACE_NET_DIR, build_feedback_graph


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild TRACE-Net feedback graph overlay from feedback_events.jsonl.")
    parser.add_argument("--trace-net-dir", default=str(TRACE_NET_DIR))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    trace_net_dir = Path(args.trace_net_dir)
    output_dir = Path(args.output_dir) if args.output_dir else trace_net_dir / "feedback"
    paths = FeedbackPaths(trace_net_dir=trace_net_dir, output_dir=output_dir)
    result = build_feedback_graph(paths)
    summary = result["summary"]
    print("TRACE-Net feedback graph builder")
    print(f"  Status: {summary['status']}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in ["feedback_events", "thumbs_up_events", "thumbs_down_events", "neutral_events", "context_valid_events", "context_warning_events", "policy_signal_eligible_events", "policy_signal_records", "graph_nodes", "graph_edges"]:
        print(f"    {key}: {summary.get(key)}")
    print("Files written:")
    print(f"  events: {paths.feedback_events}")
    print(f"  summary: {paths.summary}")
    print(f"  policy_signals: {paths.policy_signals}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")
    print(f"  review_html: {paths.review_html}")
    if args.open:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
