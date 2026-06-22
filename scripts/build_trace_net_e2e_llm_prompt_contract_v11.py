#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_llm_prompt_contract_v11 import (  # noqa: E402
    QUALITY_PASS,
    add_quality_args,
    build_llm_prompt_contract_report,
    evaluate_quality,
    read_json,
    write_report_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E LLM prompt contract v11 artifact.")
    parser.add_argument("--dynamic-context-pack", required=True)
    parser.add_argument("--self-rag-context-critic", required=True)
    parser.add_argument("--crag-retrieval-corrector", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    add_quality_args(parser)
    args = parser.parse_args()

    dynamic_context_pack = read_json(args.dynamic_context_pack)
    self_rag_context_critic = read_json(args.self_rag_context_critic)
    crag_retrieval_corrector = read_json(args.crag_retrieval_corrector)
    report = build_llm_prompt_contract_report(
        dynamic_context_pack,
        self_rag_context_critic,
        crag_retrieval_corrector,
        source_paths={
            "dynamic_context_pack": args.dynamic_context_pack,
            "self_rag_context_critic": args.self_rag_context_critic,
            "crag_retrieval_corrector": args.crag_retrieval_corrector,
        },
    )
    quality_status, checks = evaluate_quality(report, args)
    report["quality_status"] = quality_status
    report["summary"]["quality_status"] = quality_status
    report["quality_checks"] = checks
    paths = write_report_files(report, args.output_dir)

    print("TRACE-Net E2E LLM Prompt Contract v11")
    print(f" Status: {report.get('e2e_llm_prompt_contract_status')}")
    print(f" Quality status: {quality_status}")
    summary = report["summary"]
    for key in [
        "context_pack_count",
        "prompt_contract_count",
        "ready_prompt_contract_count",
        "total_prompt_message_count",
        "contracts_with_source_truth_evidence_count",
        "contracts_with_guidance_box_count",
        "contracts_with_self_rag_ready_count",
        "contracts_with_crag_no_retry_count",
        "contracts_with_graph_or_summary_guidance_count",
        "graph_summary_proof_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    for key, value in paths.items():
        print(f" {key}: {value}")

    if args.quality and quality_status != QUALITY_PASS:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
