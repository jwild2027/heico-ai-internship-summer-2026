#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net E2E RAG demo report v1 quality")
    p.add_argument("--report-path", required=True)
    p.add_argument("--min-stage-passes", type=int, default=5)
    p.add_argument("--min-demo-records", type=int, default=5)
    p.add_argument("--min-complete-demo-flows", type=int, default=5)
    p.add_argument("--min-route-plans", type=int, default=5)
    p.add_argument("--min-total-tunnels", type=int, default=15)
    p.add_argument("--min-retrieval-groups", type=int, default=5)
    p.add_argument("--min-successful-retrieval-queries", type=int, default=4)
    p.add_argument("--min-context-packs", type=int, default=5)
    p.add_argument("--min-final-gate-ready-packs", type=int, default=4)
    p.add_argument("--min-final-gate-records", type=int, default=5)
    p.add_argument("--min-safe-response-drafts", type=int, default=4)
    p.add_argument("--min-citation-backed-response-drafts", type=int, default=4)
    p.add_argument("--min-total-citations", type=int, default=10)
    p.add_argument("--min-pages-cited", type=int, default=2)
    p.add_argument("--min-field-count", type=int, default=3)
    p.add_argument("--max-schema-missing-required-key-records", type=int, default=0)
    p.add_argument("--max-unsafe-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--write-json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    path = Path(args.report_path)
    with path.open("r", encoding="utf-8") as f:
        report = json.load(f)
    checks = report.get("quality_checks", [])
    status = "PASS" if report.get("quality_status") == "PASS" and all(c.get("passed") for c in checks) else "FAIL"
    print("TRACE-Net E2E RAG Demo Report v1 Quality")
    print(f" quality_status: {status}")
    for c in checks:
        line_status = "PASS" if c.get("passed") else "FAIL"
        print(f" {line_status} {c.get('name')}: observed={c.get('observed')} expected={c.get('expected')}")
    if args.write_json:
        quality_path = path.with_name("trace_net_e2e_rag_demo_report_v1_quality.json")
        quality_path.write_text(json.dumps({"quality_status": status, "quality_checks": checks, "summary": report.get("summary", {})}, indent=2), encoding="utf-8")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
