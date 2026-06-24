from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from pathlib import Path

from tiff.trace_net_e2e_image_visual_observer_route_v34_1 import build_report


def main() -> int:
    ap = argparse.ArgumentParser(description="Build TRACE-Net E2E Image Visual Observer Route v34.1")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8030)
    ap.add_argument("--llm-mode", choices=["simulate", "ollama"], default="simulate")
    ap.add_argument("--llm-base-url", default="http://127.0.0.1:11434")
    ap.add_argument("--llm-model", default="llava:13b")
    ap.add_argument("--request-timeout", type=int, default=180)
    ap.add_argument("--include-standard-demo-queries", action="store_true")
    ap.add_argument("--sample-image-path", action="append", default=[])
    ap.add_argument("--min-sample-queries", type=int, default=0)
    ap.add_argument("--min-sample-successes", type=int, default=0)
    ap.add_argument("--min-visual-packages", type=int, default=0)
    ap.add_argument("--min-image-quality-cards", type=int, default=0)
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
    ap.add_argument("--quality", action="store_true")
    args = ap.parse_args()

    report = build_report(
        output_dir=args.output_dir,
        host=args.host,
        port=args.port,
        llm_mode=args.llm_mode,
        llm_model=args.llm_model,
        llm_base_url=args.llm_base_url,
        request_timeout=args.request_timeout,
        include_standard_demo_queries=args.include_standard_demo_queries,
        sample_image_paths=args.sample_image_path,
    )

    from tiff.trace_net_e2e_image_visual_observer_route_v34_1 import evaluate_quality, _write_json

    checks = evaluate_quality(
        report,
        min_sample_queries=args.min_sample_queries,
        min_sample_successes=args.min_sample_successes,
        min_visual_packages=args.min_visual_packages,
        min_image_quality_cards=args.min_image_quality_cards,
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
    report["quality_checks"] = checks
    report["quality_status"] = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    _write_json(report["report_path"], report)

    print("TRACE-Net E2E Image Visual Observer Route v34.1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "sample_query_count",
        "sample_success_count",
        "visual_package_count",
        "image_quality_card_count",
        "visual_observation_card_count",
        "llava_observer_card_count",
        "guidance_only_visual_card_count",
        "self_rag_sample_count",
        "crag_sample_count",
        "crag_retry_required_count",
        "diagram_draft_card_count",
        "diagram_draft_available_count",
        "diagram_draft_guidance_only_count",
        "visual_proof_authority_violation_count",
        "unsupported_visual_claim_count",
        "post_gate_issue_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        print(f" {key}: {report.get(key)}")
    print(f" base_url_windows: {report.get('base_url_windows')}")
    print(f" base_url_open_webui_docker: {report.get('base_url_open_webui_docker')}")
    print(f" report_path: {report.get('report_path')}")
    if args.quality and report.get("quality_status") != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
