#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_context_pack_builder_v1 import QUALITY_FAIL, QUALITY_PASS, _write_json, evaluate_quality


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E context pack builder quality.")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-source-retrieval-groups", type=int, default=5)
    parser.add_argument("--min-context-packs", type=int, default=5)
    parser.add_argument("--min-context-packs-with-items", type=int, default=4)
    parser.add_argument("--min-total-context-items", type=int, default=10)
    parser.add_argument("--min-pages-with-context-items", type=int, default=2)
    parser.add_argument("--min-citation-ready-items", type=int, default=10)
    parser.add_argument("--min-source-trace-ready-items", type=int, default=10)
    parser.add_argument("--min-field-count", type=int, default=3)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-runtime-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = read_json(args.report_path)
    quality_status, checks = evaluate_quality(report, args)
    report["quality_status"] = quality_status
    report["quality_checks"] = checks
    if args.write_json:
        _write_json(args.report_path, report)
        quality_path = args.report_path.with_name("trace_net_e2e_context_pack_builder_v1_quality.json")
        _write_json(quality_path, {"quality_status": quality_status, "quality_checks": checks, "summary": report.get("summary", {})})
    print("TRACE-Net E2E Context Pack Builder v1 Quality")
    print(f" quality_status: {quality_status}")
    for check in checks:
        status = "PASS" if check.get("passed") else "FAIL"
        print(f" {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return 0 if quality_status == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
