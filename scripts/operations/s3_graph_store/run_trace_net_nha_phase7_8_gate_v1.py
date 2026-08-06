#!/usr/bin/env python3
"""Run TRACE-Net NHA N7 shadow and N8 gated sidecar release gates."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trace_net.graph.trace_net_nha_phase6_query_benchmark_v1 import build_real_smoke_cases
from src.trace_net.graph.trace_net_nha_phase7_8_runtime_v1 import (
    NHAIntegrationAdapter,
    build_gate_bank,
    evaluate_gate_bank,
    load_real_engine,
    validate_gate_results,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase4-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-case-count", type=int, default=40)
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    engine, source = load_real_engine(args.phase4_dir, max_depth=args.max_depth)
    real_cases = build_real_smoke_cases(source["answer_key"], maximum=20)
    bank = build_gate_bank(real_cases, source["relationships"], total=args.expected_case_count)

    shadow_adapter = NHAIntegrationAdapter(
        engine,
        mode="shadow",
        telemetry_path=output / "trace_net_nha_phase7_shadow_telemetry_v1.jsonl",
    )
    gated_adapter = NHAIntegrationAdapter(
        engine,
        mode="gated",
        telemetry_path=output / "trace_net_nha_phase8_gated_telemetry_v1.jsonl",
    )
    shadow_results = evaluate_gate_bank(bank, shadow_adapter)
    gated_results = evaluate_gate_bank(bank, gated_adapter)
    quality = validate_gate_results(
        shadow_results,
        gated_results,
        expected_count=args.expected_case_count,
    )

    write_json(output / "trace_net_nha_phase7_8_gate_bank_v1.json", {"records": bank})
    write_json(output / "trace_net_nha_phase7_shadow_results_v1.json", {"records": shadow_results})
    write_jsonl(output / "trace_net_nha_phase7_shadow_results_v1.jsonl", shadow_results)
    write_json(output / "trace_net_nha_phase8_gated_results_v1.json", {"records": gated_results})
    write_jsonl(output / "trace_net_nha_phase8_gated_results_v1.jsonl", gated_results)
    write_json(output / "trace_net_nha_phase7_8_quality_v1.json", quality)

    report = [
        "# TRACE-Net NHA N7-N8 Gate",
        "",
        f"- Quality: **{quality['quality_status']}**",
        f"- Shadow: {quality['counts']['shadow_pass_count']}/{quality['counts']['shadow_case_count']}",
        f"- Gated: {quality['counts']['gated_pass_count']}/{quality['counts']['gated_case_count']}",
        f"- Shadow overrides: {quality['counts']['shadow_override_count']}",
        f"- Gated overrides: {quality['counts']['gated_override_count']}",
        f"- Public contracts: {quality['counts']['gated_public_contract_pass_count']}",
        f"- Synthetic access: {quality['counts']['synthetic_access_count']}",
        "",
        "## Failures",
        *([f"- {value}" for value in quality["failures"]] or ["- None"]),
    ]
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    summary = {
        "schema_version": "trace_net_nha_phase7_8_runtime_v1",
        "module": "trace_net_nha_phase7_8_runtime_v1",
        "status": "TRACE_NET_NHA_PHASE7_8_RUNTIME_V1",
        "quality_status": quality["quality_status"],
        "phase4_dir": source["phase4_dir"],
        "output_dir": str(output),
        "input_sha256": {
            "relationships": source["relationship_sha256"],
            "quality": source["quality_sha256"],
            "answer_key": source["answer_key_sha256"],
        },
        "counts": quality["counts"],
        "failures": quality["failures"],
        "warnings": quality["warnings"],
        "artifacts": [
            "trace_net_nha_phase7_8_gate_bank_v1.json",
            "trace_net_nha_phase7_shadow_results_v1.json",
            "trace_net_nha_phase7_shadow_results_v1.jsonl",
            "trace_net_nha_phase7_shadow_telemetry_v1.jsonl",
            "trace_net_nha_phase8_gated_results_v1.json",
            "trace_net_nha_phase8_gated_results_v1.jsonl",
            "trace_net_nha_phase8_gated_telemetry_v1.jsonl",
            "trace_net_nha_phase7_8_quality_v1.json",
            "report.md",
        ],
    }
    write_json(output / "trace_net_nha_phase7_8_summary_v1.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"quality_status={summary['quality_status']}")
    print(f"summary={output / 'trace_net_nha_phase7_8_summary_v1.json'}")
    if args.strict and summary["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE7_8=FAIL")
    print("TRACE_NET_NHA_PHASE7_8=PASS" if summary["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE7_8=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
