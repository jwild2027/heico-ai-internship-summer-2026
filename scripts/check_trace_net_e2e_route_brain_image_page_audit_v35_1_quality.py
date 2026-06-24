from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import argparse
import json
from pathlib import Path
from tiff.trace_net_e2e_route_brain_image_page_audit_v35_1 import _write_json, evaluate_quality


def main() -> int:
    ap = argparse.ArgumentParser(description="Check route brain image page audit v35.1 quality")
    ap.add_argument("--report-path", required=True)
    ap.add_argument("--min-source-pages", type=int, default=1)
    ap.add_argument("--min-route-candidates", type=int, default=1)
    ap.add_argument("--min-manual-screened-diagram-pages", type=int, default=1)
    ap.add_argument("--expected-actual-diagram-pages", type=int, default=None)
    ap.add_argument("--max-image-visual-candidates-after-correction", type=int, default=None)
    ap.add_argument("--min-overbroad-image-visual-candidates", type=int, default=0)
    ap.add_argument("--max-malformed-route-values", type=int, default=0)
    ap.add_argument("--max-visual-proof-authority-violations", type=int, default=0)
    ap.add_argument("--max-post-gate-issue-count", type=int, default=0)
    ap.add_argument("--max-answer-permission-count", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--require-no-answer-permission", action="store_true")
    ap.add_argument("--write-json", action="store_true")
    args = ap.parse_args()
    path = Path(args.report_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    status, checks = evaluate_quality(
        data,
        min_source_pages=args.min_source_pages,
        min_route_candidates=args.min_route_candidates,
        min_manual_screened_diagram_pages=args.min_manual_screened_diagram_pages,
        expected_actual_diagram_pages=args.expected_actual_diagram_pages,
        max_image_visual_candidates_after_correction=args.max_image_visual_candidates_after_correction,
        min_overbroad_image_visual_candidates=args.min_overbroad_image_visual_candidates,
        max_malformed_route_values=args.max_malformed_route_values,
        max_visual_proof_authority_violations=args.max_visual_proof_authority_violations,
        max_post_gate_issue_count=args.max_post_gate_issue_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    data["quality_status"] = status
    data["quality_checks"] = checks
    print("TRACE-Net Route Brain Image Page Audit v35.1 Quality")
    print(" quality_status:", status)
    for c in checks:
        print(f" {c['status']} {c['name']}: observed={c['observed']} expected={c['expected']}")
    if args.write_json:
        _write_json(path, data)
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
