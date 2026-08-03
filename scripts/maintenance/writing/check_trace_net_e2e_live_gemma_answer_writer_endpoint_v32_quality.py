from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_gemma_answer_writer_endpoint_v32 import check_report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-path", required=True)
    ap.add_argument("--min-sample-queries", type=int, default=0)
    ap.add_argument("--min-sample-successes", type=int, default=0)
    ap.add_argument("--min-llm-called-samples", type=int, default=0)
    ap.add_argument("--min-compact-prompt-samples", type=int, default=0)
    ap.add_argument("--min-normal-intent-samples", type=int, default=0)
    ap.add_argument("--max-post-gate-issue-count", type=int, default=0)
    ap.add_argument("--max-answer-permission-count", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--require-no-answer-permission", action="store_true")
    ap.add_argument("--write-json", action="store_true")
    ns = ap.parse_args(argv)
    p = Path(ns.report_path)
    data = json.loads(p.read_text(encoding="utf-8"))
    checks = check_report(
        data,
        min_sample_queries=ns.min_sample_queries,
        min_sample_successes=ns.min_sample_successes,
        min_llm_called_samples=ns.min_llm_called_samples,
        min_compact_prompt_samples=ns.min_compact_prompt_samples,
        min_normal_intent_samples=ns.min_normal_intent_samples,
        max_post_gate_issue_count=ns.max_post_gate_issue_count,
        max_answer_permission_count=ns.max_answer_permission_count,
        max_source_truth_mutation_allowed=ns.max_source_truth_mutation_allowed,
        require_no_answer_permission=ns.require_no_answer_permission,
    )
    ok = all(c["passed"] for c in checks)
    data["quality_checks"] = checks
    data["quality_status"] = "PASS" if ok else "FAIL"
    if ns.write_json:
        p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    print("TRACE-Net E2E Live Gemma Answer Writer Endpoint v32 Quality")
    print(" quality_status:", data["quality_status"])
    for c in checks:
        status = "PASS" if c["passed"] else "FAIL"
        print(f" {status} {c['name']}: observed={c['observed']} expected={c['op']} {c['expected']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
