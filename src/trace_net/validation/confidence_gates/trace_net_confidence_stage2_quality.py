"""Quality gate for TRACE-Net Layer Confidence Stage 2 evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import argparse
import json


@dataclass(frozen=True)
class ConfidenceStage2QualityPaths:
    eval_json: Path = Path("local_data/organization/trace_net/confidence/trace_lc_stage2_eval.json")
    quality_json: Path = Path("local_data/organization/trace_net/confidence/trace_lc_stage2_quality.json")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def build_confidence_stage2_quality(
    paths: ConfidenceStage2QualityPaths,
    *,
    min_records: int = 1,
    require_all_scored: bool = True,
    min_layers: int = 1,
    max_missing_confidence_records: int = 0,
) -> dict[str, Any]:
    report = _read_json(paths.eval_json, default={}) or {}
    present = paths.eval_json.exists()
    per_layer = report.get("per_layer") if isinstance(report.get("per_layer"), dict) else {}

    summary = {
        "trace_lc_stage2_report_present": present,
        "trace_lc_stage2_status": report.get("status"),
        "trace_lc_stage2_records": int(report.get("records") or 0),
        "trace_lc_stage2_scored_records": int(report.get("scored_records") or 0),
        "trace_lc_stage2_missing_confidence_records": int(report.get("missing_confidence_records") or 0),
        "trace_lc_stage2_agreement_rate": report.get("agreement_rate"),
        "trace_lc_stage2_disagreement_records": int(report.get("disagreement_records") or 0),
        "trace_lc_stage2_within_one_tier_rate": report.get("within_one_tier_rate"),
        "trace_lc_stage2_confidence_higher_records": int(report.get("confidence_higher_records") or 0),
        "trace_lc_stage2_confidence_lower_records": int(report.get("confidence_lower_records") or 0),
        "trace_lc_stage2_rule_includes_confidence_low_records": int(report.get("rule_includes_confidence_low_records") or 0),
        "trace_lc_stage2_rule_excludes_confidence_high_records": int(report.get("rule_excludes_confidence_high_records") or 0),
        "trace_lc_stage2_blocked_high_confidence_records": int(report.get("blocked_high_confidence_records") or 0),
        "trace_lc_stage2_source_trace_confidence_below_A_records": int(report.get("source_trace_confidence_below_A_records") or 0),
        "trace_lc_stage2_avg_usable_confidence": report.get("avg_usable_confidence"),
        "trace_lc_stage2_layers": len(per_layer),
        "trace_lc_stage2_eval_path": str(paths.eval_json),
    }

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("report_present", present, f"Report present at {paths.eval_json}: {present}.")
    add("status_ok", report.get("status") == "OK", f"Report status is {report.get('status')}.")
    add("records", summary["trace_lc_stage2_records"] >= min_records, f"records={summary['trace_lc_stage2_records']}; minimum={min_records}.")
    if require_all_scored:
        add(
            "all_records_scored",
            summary["trace_lc_stage2_missing_confidence_records"] <= max_missing_confidence_records,
            f"missing confidence records={summary['trace_lc_stage2_missing_confidence_records']}; max={max_missing_confidence_records}.",
        )
    add("layers", summary["trace_lc_stage2_layers"] >= min_layers, f"layers={summary['trace_lc_stage2_layers']}; minimum={min_layers}.")
    add(
        "has_disagreement_metric",
        "disagreement_records" in report,
        f"disagreement_records={report.get('disagreement_records')}.",
    )
    add(
        "has_per_layer_metrics",
        bool(per_layer),
        f"per_layer entries={len(per_layer)}.",
    )

    status = "OK" if all(c["ok"] for c in checks) else "FAIL"
    return {"status": status, "summary": summary, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Layer Confidence Stage 2 quality.")
    parser.add_argument("--eval-json", type=Path, default=ConfidenceStage2QualityPaths.eval_json)
    parser.add_argument("--quality", type=Path, default=ConfidenceStage2QualityPaths.quality_json)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-layers", type=int, default=1)
    parser.add_argument("--max-missing-confidence-records", type=int, default=0)
    parser.add_argument("--allow-missing-confidence", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    paths = ConfidenceStage2QualityPaths(eval_json=args.eval_json, quality_json=args.quality)
    quality = build_confidence_stage2_quality(
        paths,
        min_records=args.min_records,
        require_all_scored=not args.allow_missing_confidence,
        min_layers=args.min_layers,
        max_missing_confidence_records=args.max_missing_confidence_records,
    )

    print("TRACE-Net Layer Confidence Stage 2 quality gate")
    print(f"  Status: {quality['status']}")
    print("  Summary:")
    for key, value in quality["summary"].items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in quality["checks"]:
        prefix = "OK" if check["ok"] else "FAIL"
        print(f"    {prefix} {check['name']}: {check['detail']}")

    if args.write_json:
        _write_json(paths.quality_json, quality)
        print(f"\nJSON: {paths.quality_json}")

    return 0 if quality["status"] == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
