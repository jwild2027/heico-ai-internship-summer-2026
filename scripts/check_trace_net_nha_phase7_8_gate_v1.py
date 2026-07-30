#!/usr/bin/env python3
"""Check TRACE-Net NHA N7-N8 gate artifacts independently."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def records(path: Path) -> list[dict]:
    payload = read_json(path)
    return list(payload.get("records") or []) if isinstance(payload, dict) else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-case-count", type=int, default=40)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.output_dir).resolve()
    required = {
        "bank": root / "trace_net_nha_phase7_8_gate_bank_v1.json",
        "shadow": root / "trace_net_nha_phase7_shadow_results_v1.json",
        "gated": root / "trace_net_nha_phase8_gated_results_v1.json",
        "quality": root / "trace_net_nha_phase7_8_quality_v1.json",
        "summary": root / "trace_net_nha_phase7_8_summary_v1.json",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    failures: list[str] = []
    if missing:
        failures.append("missing_artifacts:" + ",".join(missing))
        bank = shadow = gated = []
        quality = summary = {}
    else:
        bank = records(required["bank"])
        shadow = records(required["shadow"])
        gated = records(required["gated"])
        quality = read_json(required["quality"])
        summary = read_json(required["summary"])
    if len(bank) != args.expected_case_count:
        failures.append(f"bank_count expected={args.expected_case_count} actual={len(bank)}")
    if len(shadow) != args.expected_case_count:
        failures.append(f"shadow_count expected={args.expected_case_count} actual={len(shadow)}")
    if len(gated) != args.expected_case_count:
        failures.append(f"gated_count expected={args.expected_case_count} actual={len(gated)}")
    if any(not row.get("passed") for row in shadow):
        failures.append("shadow_failed_records")
    if any(not row.get("passed") for row in gated):
        failures.append("gated_failed_records")
    if any((row.get("decision") or {}).get("override") for row in shadow):
        failures.append("shadow_override")
    if any(
        (row.get("decision") or {}).get("override")
        for row in gated
        if row.get("kind") in {"non_nha_control", "synthetic_block_control"}
    ):
        failures.append("false_gated_override")
    if any((row.get("decision") or {}).get("synthetic_access_count") for row in [*shadow, *gated]):
        failures.append("synthetic_access")
    if quality.get("quality_status") != "PASS":
        failures.append("quality_artifact_not_pass")
    if summary.get("quality_status") != "PASS":
        failures.append("summary_not_pass")
    result = {
        "schema_version": "trace_net_nha_phase7_8_runtime_v1",
        "module": "check_trace_net_nha_phase7_8_gate_v1",
        "status": "TRACE_NET_NHA_PHASE7_8_CHECK_V1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": [],
        "counts": {
            "bank_case_count": len(bank),
            "shadow_case_count": len(shadow),
            "shadow_pass_count": sum(bool(row.get("passed")) for row in shadow),
            "gated_case_count": len(gated),
            "gated_pass_count": sum(bool(row.get("passed")) for row in gated),
            "shadow_override_count": sum(bool((row.get("decision") or {}).get("override")) for row in shadow),
            "gated_override_count": sum(bool((row.get("decision") or {}).get("override")) for row in gated),
            "synthetic_access_count": sum(int((row.get("decision") or {}).get("synthetic_access_count") or 0) for row in [*shadow, *gated]),
        },
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.strict and result["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE7_8_CHECK=FAIL")
    print("TRACE_NET_NHA_PHASE7_8_CHECK=PASS" if result["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE7_8_CHECK=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
