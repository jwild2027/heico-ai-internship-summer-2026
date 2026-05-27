#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import webbrowser

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.pipeline_quality import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    QualityGateThresholds,
    check_pipeline_manifest_file,
    format_quality_gate_result,
    write_quality_gate_html,
    write_quality_gate_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the latest TIFF backend pipeline manifest against quality gates.")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output-dir", default="local_data/pipeline_runs")
    parser.add_argument("--max-eval-failures", type=int, default=0)
    parser.add_argument("--max-manual-review", type=int, default=1)
    parser.add_argument("--max-qa-review", type=int, default=250)
    parser.add_argument("--max-suspicious-part-ata", type=int, default=10)
    parser.add_argument("--strict", action="store_true", help="Return a non-zero code for REVIEW as well as FAIL.")
    parser.add_argument("--open", action="store_true", help="Open the generated HTML quality report.")
    args = parser.parse_args()

    thresholds = QualityGateThresholds(
        max_eval_failures=args.max_eval_failures,
        max_manual_review=args.max_manual_review,
        max_qa_review=args.max_qa_review,
        max_suspicious_part_ata=args.max_suspicious_part_ata,
    )
    result = check_pipeline_manifest_file(args.manifest, thresholds=thresholds)

    output_dir = Path(args.output_dir)
    json_path = write_quality_gate_json(result, output_dir / "latest_quality_gate.json")
    html_path = write_quality_gate_html(result, output_dir / "latest_quality_gate.html")

    print(format_quality_gate_result(result))
    print(f"\nQuality JSON: {json_path}")
    print(f"Quality HTML: {html_path}")

    if args.open:
        webbrowser.open(html_path.resolve().as_uri())

    if result.status == "fail":
        return 1
    if args.strict and result.status == "review":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
