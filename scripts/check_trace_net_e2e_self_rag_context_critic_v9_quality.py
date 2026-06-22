#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def check(name: str, observed, expected: str, passed: bool):
    return {"name": name, "observed": observed, "expected": expected, "passed": bool(passed)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E Self-RAG Context Critic v9 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-context-packs", type=int, default=1)
    parser.add_argument("--min-context-critiques", type=int, default=1)
    parser.add_argument("--min-ready-contexts", type=int, default=1)
    parser.add_argument("--min-contexts-with-source-truth-evidence", type=int, default=1)
    parser.add_argument("--min-contexts-with-guidance-separation", type=int, default=1)
    parser.add_argument("--max-needs-crag-retry-count", type=int, default=None)
    parser.add_argument("--max-human-review-count", type=int, default=0)
    parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = dict(report.get("summary") or {})

    checks = [
        check("quality_status", report.get("quality_status"), "== PASS", report.get("quality_status") == "PASS"),
        check("context_pack_count", summary.get("context_pack_count", 0), f">= {args.min_context_packs}", summary.get("context_pack_count", 0) >= args.min_context_packs),
        check("self_rag_critique_count", summary.get("self_rag_critique_count", 0), f">= {args.min_context_critiques}", summary.get("self_rag_critique_count", 0) >= args.min_context_critiques),
        check("ready_context_count", summary.get("ready_context_count", 0), f">= {args.min_ready_contexts}", summary.get("ready_context_count", 0) >= args.min_ready_contexts),
        check("contexts_with_source_truth_evidence_count", summary.get("contexts_with_source_truth_evidence_count", 0), f">= {args.min_contexts_with_source_truth_evidence}", summary.get("contexts_with_source_truth_evidence_count", 0) >= args.min_contexts_with_source_truth_evidence),
        check("contexts_with_guidance_separation_count", summary.get("contexts_with_guidance_separation_count", 0), f">= {args.min_contexts_with_guidance_separation}", summary.get("contexts_with_guidance_separation_count", 0) >= args.min_contexts_with_guidance_separation),
        check("human_review_count", summary.get("human_review_count", 0), f"<= {args.max_human_review_count}", summary.get("human_review_count", 0) <= args.max_human_review_count),
        check("graph_summary_proof_violation_count", summary.get("graph_summary_proof_violation_count", 0), f"<= {args.max_graph_summary_proof_violations}", summary.get("graph_summary_proof_violation_count", 0) <= args.max_graph_summary_proof_violations),
        check("answer_permission_count", summary.get("answer_permission_count", 0), f"<= {args.max_answer_permission_count}", summary.get("answer_permission_count", 0) <= args.max_answer_permission_count),
        check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), f"<= {args.max_source_truth_mutation_allowed}", summary.get("source_truth_mutation_allowed_count", 0) <= args.max_source_truth_mutation_allowed),
        check("contract_can_answer_directly", summary.get("can_answer_directly_count", 0), "== 0", summary.get("can_answer_directly_count", 0) == 0),
        check("contract_can_prove_claims", summary.get("can_prove_claims_count", 0), "== 0", summary.get("can_prove_claims_count", 0) == 0),
    ]
    if args.max_needs_crag_retry_count is not None:
        checks.append(check("needs_crag_retry_count", summary.get("needs_crag_retry_count", 0), f"<= {args.max_needs_crag_retry_count}", summary.get("needs_crag_retry_count", 0) <= args.max_needs_crag_retry_count))
    if args.require_no_answer_permission:
        checks.append(check("require_no_answer_permission", summary.get("answer_permission_count", 0), "== 0", summary.get("answer_permission_count", 0) == 0))

    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    print("TRACE-Net E2E Self-RAG Context Critic v9 Quality")
    print(f" quality_status: {quality_status}")
    for c in checks:
        print(f" {'PASS' if c['passed'] else 'FAIL'} {c['name']}: observed={c['observed']} expected={c['expected']}")

    if args.write_json:
        out = report_path.with_name(report_path.stem + "_quality.json")
        out.write_text(json.dumps({"quality_status": quality_status, "quality_checks": checks}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
