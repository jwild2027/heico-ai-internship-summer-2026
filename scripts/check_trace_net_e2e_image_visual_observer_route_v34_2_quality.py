from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
from pathlib import Path

from tiff.trace_net_e2e_image_visual_observer_route_v34_2 import evaluate_quality, _write_json


def main() -> int:
    ap = argparse.ArgumentParser(description="Check TRACE-Net E2E Image Visual Observer Route v34.2 quality")
    ap.add_argument("--report-path", required=True)
    ap.add_argument("--min-sample-queries", type=int, default=0)
    ap.add_argument("--min-sample-successes", type=int, default=0)
    ap.add_argument("--min-visual-packages", type=int, default=0)
    ap.add_argument("--min-image-quality-cards", type=int, default=0)
    ap.add_argument("--min-ocr-text-cards", type=int, default=0)
    ap.add_argument("--min-opencv-layout-cards", type=int, default=0)
    ap.add_argument("--min-grounded-visual-packages", type=int, default=0)
    ap.add_argument("--min-visual-observation-cards", type=int, default=0)
    ap.add_argument("--min-llava-observer-cards", type=int, default=0)
    ap.add_argument("--min-guidance-only-visual-cards", type=int, default=0)
    ap.add_argument("--min-self-rag-samples", type=int, default=0)
    ap.add_argument("--min-crag-samples", type=int, default=0)
    ap.add_argument("--min-diagram-draft-cards", type=int, default=0)
    ap.add_argument("--min-guidance-only-diagram-drafts", type=int, default=0)
    ap.add_argument("--max-visual-proof-authority-violations", type=int, default=0)
    ap.add_argument("--max-unsupported-visual-claim-count", type=int, default=0)
    ap.add_argument("--max-post-gate-issue-count", type=int, default=0)
    ap.add_argument("--max-answer-permission-count", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--require-no-answer-permission", action="store_true")
    ap.add_argument("--write-json", action="store_true")
    args = ap.parse_args()

    data = json.loads(Path(args.report_path).read_text(encoding="utf-8"))
    checks = evaluate_quality(
        data,
        min_sample_queries=args.min_sample_queries,
        min_sample_successes=args.min_sample_successes,
        min_visual_packages=args.min_visual_packages,
        min_image_quality_cards=args.min_image_quality_cards,
        min_ocr_text_cards=args.min_ocr_text_cards,
        min_opencv_layout_cards=args.min_opencv_layout_cards,
        min_grounded_visual_packages=args.min_grounded_visual_packages,
        min_visual_observation_cards=args.min_visual_observation_cards,
        min_llava_observer_cards=args.min_llava_observer_cards,
        min_guidance_only_visual_cards=args.min_guidance_only_visual_cards,
        min_self_rag_samples=args.min_self_rag_samples,
        min_crag_samples=args.min_crag_samples,
        min_diagram_draft_cards=args.min_diagram_draft_cards,
        min_guidance_only_diagram_drafts=args.min_guidance_only_diagram_drafts,
        max_visual_proof_authority_violations=args.max_visual_proof_authority_violations,
        max_unsupported_visual_claim_count=args.max_unsupported_visual_claim_count,
        max_post_gate_issue_count=args.max_post_gate_issue_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    data["quality_checks"] = checks
    data["quality_status"] = quality_status
    if args.write_json:
        _write_json(args.report_path, data)
    print("TRACE-Net E2E Image Visual Observer Route v34.2 Quality")
    print(f" quality_status: {quality_status}")
    for c in checks:
        status = "PASS" if c["passed"] else "FAIL"
        print(f" {status} {c['name']}: observed={c['observed']} expected={c['expected']}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
