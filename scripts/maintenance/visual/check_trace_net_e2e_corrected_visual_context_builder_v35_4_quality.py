from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_corrected_visual_context_builder_v35_4 import quality_checks, _write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net corrected visual context builder v35.4 quality.")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-source-pages", type=int, default=1)
    parser.add_argument("--min-route-decisions", type=int, default=1)
    parser.add_argument("--min-visual-context-input-pages", type=int, default=1)
    parser.add_argument("--min-visual-context-cards", type=int, default=1)
    parser.add_argument("--min-visual-prompt-contexts", type=int, default=1)
    parser.add_argument("--min-guidance-only-visual-contexts", type=int, default=1)
    parser.add_argument("--max-fishnet-visual-review-pages-processed", type=int, default=0)
    parser.add_argument("--max-overbroad-old-route-pages-processed", type=int, default=0)
    parser.add_argument("--max-missing-source-page-records", type=int, default=0)
    parser.add_argument("--max-visual-proof-authority-violations", type=int, default=0)
    parser.add_argument("--max-post-gate-issue-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    report: Dict[str, Any] = json.loads(args.report_path.read_text(encoding="utf-8"))
    checks: List[Dict[str, Any]] = quality_checks(report, args)
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    report["quality_checks"] = checks
    report["quality_status"] = quality_status
    if args.write_json:
        _write_json(args.report_path, report)

    print("TRACE-Net Corrected Visual Context Builder v35.4 Quality")
    print(" quality_status:", quality_status)
    for c in checks:
        prefix = "PASS" if c["passed"] else "FAIL"
        print(f" {prefix} {c['name']}: observed={c['observed']} expected={c['expected']}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
