from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_route_scoped_visual_context_builder_v35 import apply_quality, evaluate_quality


def main() -> int:
    ap = argparse.ArgumentParser(description="Check TRACE-Net route-scoped visual context builder v35 quality")
    ap.add_argument("--report-path", required=True)
    ap.add_argument("--min-source-pages", type=int, default=0)
    ap.add_argument("--min-route-candidates", type=int, default=0)
    ap.add_argument("--min-image-visual-candidates", type=int, default=0)
    ap.add_argument("--min-visual-context-cards", type=int, default=0)
    ap.add_argument("--min-visual-prompt-contexts", type=int, default=0)
    ap.add_argument("--min-guidance-only-visual-contexts", type=int, default=0)
    ap.add_argument("--min-technical-geometry-cards", type=int, default=0)
    ap.add_argument("--max-visual-proof-authority-violations", type=int, default=0)
    ap.add_argument("--max-post-gate-issue-count", type=int, default=0)
    ap.add_argument("--max-answer-permission-count", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--require-no-answer-permission", action="store_true")
    ap.add_argument("--write-json", action="store_true")
    args = ap.parse_args()
    p = Path(args.report_path)
    report = json.loads(p.read_text(encoding="utf-8"))
    checks = evaluate_quality(
        report,
        min_source_pages=args.min_source_pages,
        min_route_candidates=args.min_route_candidates,
        min_image_visual_candidates=args.min_image_visual_candidates,
        min_visual_context_cards=args.min_visual_context_cards,
        min_visual_prompt_contexts=args.min_visual_prompt_contexts,
        min_guidance_only_visual_contexts=args.min_guidance_only_visual_contexts,
        min_technical_geometry_cards=args.min_technical_geometry_cards,
        max_visual_proof_authority_violations=args.max_visual_proof_authority_violations,
        max_post_gate_issue_count=args.max_post_gate_issue_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    if args.write_json:
        report = apply_quality(report, checks)
    status = "PASS" if all(c.get("passed") for c in checks) else "FAIL"
    print("TRACE-Net Route-Scoped Visual Context Builder v35 Quality")
    print(f" quality_status: {status}")
    for c in checks:
        label = "PASS" if c.get("passed") else "FAIL"
        print(f" {label} {c.get('name')}: observed={c.get('observed')} expected={c.get('operator')} {c.get('expected')}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
