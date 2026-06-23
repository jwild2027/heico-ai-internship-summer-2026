#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_dynamic_context_pack_v8 import QualityThresholds, evaluate_quality, write_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Check TRACE-Net E2E dynamic context pack v8 quality")
    p.add_argument("--report-path", required=True)
    p.add_argument("--min-context-packs", type=int, default=1)
    p.add_argument("--min-ready-context-packs", type=int, default=1)
    p.add_argument("--min-total-evidence-items", type=int, default=1)
    p.add_argument("--min-packs-with-evidence-box", type=int, default=1)
    p.add_argument("--min-packs-with-guidance-box", type=int, default=1)
    p.add_argument("--min-packs-with-rules-box", type=int, default=1)
    p.add_argument("--min-packs-with-graph-or-summary-guidance", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--write-json", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.report_path)
    report = json.loads(path.read_text(encoding="utf-8"))
    thresholds = QualityThresholds(
        min_context_packs=args.min_context_packs,
        min_ready_context_packs=args.min_ready_context_packs,
        min_total_evidence_items=args.min_total_evidence_items,
        min_packs_with_evidence_box=args.min_packs_with_evidence_box,
        min_packs_with_guidance_box=args.min_packs_with_guidance_box,
        min_packs_with_rules_box=args.min_packs_with_rules_box,
        min_packs_with_graph_or_summary_guidance=args.min_packs_with_graph_or_summary_guidance,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    checks = evaluate_quality(report.get("summary", {}), thresholds)
    quality_status = "PASS" if all(c["passed"] for c in checks) and report.get("quality_status") == "PASS" else "FAIL"
    print("TRACE-Net E2E Dynamic Context Pack v8 Quality")
    print(f" quality_status: {quality_status}")
    for check in checks:
        label = "PASS" if check["passed"] else "FAIL"
        print(f" {label} {check['name']}: observed={check['observed']} expected={check['expected']}")
    if args.write_json:
        report["quality_checks"] = checks
        report["quality_status"] = quality_status
        if quality_status == "PASS":
            report["e2e_dynamic_context_pack_status"] = "E2E_DYNAMIC_CONTEXT_PACK_READY_FOR_SELF_RAG"
        write_json(path, report)
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
