#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_claim_evidence_entailment_v1 import (
    EntailmentThresholds,
    check_claim_evidence_entailment_quality,
    print_quality_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Claim Evidence Entailment v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-entailment-records", type=int, default=1)
    parser.add_argument("--min-claim-records", type=int, default=1)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-source-resolved-records", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--require-dynamic-final-gate-quality-pass", action="store_true")
    parser.add_argument("--require-dublin-core-source-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    thresholds = EntailmentThresholds(
        min_entailment_records=args.min_entailment_records,
        min_claim_records=args.min_claim_records,
        min_queries=args.min_queries,
        min_source_resolved_records=args.min_source_resolved_records,
        max_unsafe_records=args.max_unsafe_records,
        require_dynamic_final_gate_quality_pass=args.require_dynamic_final_gate_quality_pass,
        require_dublin_core_source_quality_pass=args.require_dublin_core_source_quality_pass,
    )
    payload = check_claim_evidence_entailment_quality(
        report_path=args.report_path,
        thresholds=thresholds,
        write_json_report=args.write_json,
    )
    print_quality_summary(payload)
    return 0 if payload.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
