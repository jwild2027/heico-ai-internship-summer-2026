#!/usr/bin/env python3
"""Validate that scan quality is measured metadata and never a page route."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_scan_quality_assessment_v1 import (
    validate_route_record,
    validate_scan_quality_record,
)


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        rows = payload.get("records")
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def check(
    *,
    report_path: str | Path,
    require_scan_quality: bool = False,
    write_json: bool = False,
) -> dict[str, Any]:
    path = Path(report_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = _records(payload)
    failures: list[str] = []
    state_counts: Counter[str] = Counter()
    blur_count = 0
    missing_count = 0

    for index, row in enumerate(rows):
        route_validation = validate_route_record(row)
        if route_validation["quality_status"] != "PASS":
            failures.append(f"record_{index}_scan_quality_used_as_route")
        scan_quality = row.get("scan_quality")
        if not isinstance(scan_quality, Mapping):
            missing_count += 1
            if require_scan_quality:
                failures.append(f"record_{index}_missing_scan_quality")
            continue
        validation = validate_scan_quality_record(scan_quality)
        if validation["quality_status"] != "PASS":
            failures.extend(f"record_{index}_{item}" for item in validation["failures"])
        state_counts[str(scan_quality.get("quality_state") or "missing")] += 1
        blur_count += int(scan_quality.get("blur_detected") is True)

    failures = list(dict.fromkeys(failures))
    result = {
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "summary": {
            "record_count": len(rows),
            "scan_quality_record_count": len(rows) - missing_count,
            "missing_scan_quality_count": missing_count,
            "quality_state_counts": dict(sorted(state_counts.items())),
            "blur_detected_count": blur_count,
            "scan_quality_route_violation_count": sum("scan_quality_used_as_route" in item for item in failures),
            "scan_quality_is_not_page_route": not any("scan_quality_used_as_route" in item for item in failures),
        },
    }
    if write_json:
        out = path.with_name("trace_net_scan_quality_contract_v1_quality_check.json")
        out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print(f"wrote={out}")
    print("quality_status=" + result["quality_status"])
    print("summary=" + json.dumps(result["summary"], sort_keys=True))
    if failures:
        print("failures=" + json.dumps(failures))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-scan-quality", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    result = check(
        report_path=args.report_path,
        require_scan_quality=args.require_scan_quality,
        write_json=args.write_json,
    )
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
