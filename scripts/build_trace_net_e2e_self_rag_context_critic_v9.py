#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_self_rag_context_critic_v9 import add_common_args, build_from_args, write_report_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E Self-RAG Context Critic v9")
    add_common_args(parser)
    args = parser.parse_args()

    report = build_from_args(args)
    paths = write_report_files(report, args.output_dir)

    summary = report["summary"]
    print("TRACE-Net E2E Self-RAG Context Critic v9")
    print(f" Status: {report['e2e_self_rag_context_critic_status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "context_pack_count",
        "self_rag_critique_count",
        "ready_context_count",
        "weak_context_count",
        "needs_crag_retry_count",
        "human_review_count",
        "contexts_with_source_truth_evidence_count",
        "contexts_with_guidance_separation_count",
        "contexts_with_graph_or_summary_guidance_count",
        "graph_summary_proof_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    print(f" report_path: {paths['report_path']}")
    print(f" critiques_jsonl_path: {paths['critiques_jsonl_path']}")
    print(f" inspect_md_path: {paths['inspect_md_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
