"""Quality gate for TRACE-Net Layer Confidence Stage 4 policy simulation."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_confidence_stage4_simulation import DEFAULT_CONFIDENCE_DIR, DEFAULT_OUTPUT_JSON, SIMULATION_VERSION

DEFAULT_QUALITY = DEFAULT_CONFIDENCE_DIR / "trace_lc_stage4_policy_simulation_quality.json"


@dataclass
class Stage4QualityCheck:
    name: str
    ok: bool
    message: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Stage4QualityOptions:
    min_records: int = 1
    min_pages: int = 1
    min_layers: int = 6
    max_unsafe_policy_rag_include_records: int = 0
    min_source_trace_policy_A_records: int | None = None
    max_table_candidate_direct_rag_records: int = 0
    max_visual_text_above_B_records: int = 0
    require_policy_present: bool = True


@dataclass
class Stage4QualityReport:
    status: str
    summary: dict[str, Any]
    checks: list[Stage4QualityCheck] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "checks": [check.to_json() for check in self.checks],
        }


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _add(checks: list[Stage4QualityCheck], name: str, ok: bool, message: str) -> None:
    checks.append(Stage4QualityCheck(name=name, ok=bool(ok), message=message))


def build_stage4_quality(
    eval_path: Path = DEFAULT_OUTPUT_JSON,
    options: Stage4QualityOptions | None = None,
) -> Stage4QualityReport:
    options = options or Stage4QualityOptions()
    report = _as_dict(_read_json(eval_path, {}))
    present = bool(report)
    checks: list[Stage4QualityCheck] = []

    _add(checks, "stage4_report_present", present, f"Report present at {eval_path}: {present}.")
    _add(checks, "stage4_status", report.get("status") == "OK", f"Report status is {report.get('status')!r}.")
    _add(checks, "stage4_version", report.get("version") == SIMULATION_VERSION, f"Report version is {report.get('version')!r}.")
    _add(checks, "stage4_records", _int(report.get("records")) >= options.min_records, f"records={report.get('records')}; minimum={options.min_records}.")
    _add(checks, "stage4_pages", _int(report.get("pages")) >= options.min_pages, f"pages={report.get('pages')}; minimum={options.min_pages}.")
    _add(checks, "stage4_policy_layers", _int(report.get("policy_layers")) >= options.min_layers, f"policy_layers={report.get('policy_layers')}; minimum={options.min_layers}.")
    if options.require_policy_present:
        _add(checks, "stage4_policy_present", bool(report.get("policy_present")), f"policy_present={report.get('policy_present')}.")

    unsafe = _int(report.get("unsafe_policy_rag_include_records"))
    _add(
        checks,
        "stage4_no_unsafe_policy_rag",
        unsafe <= options.max_unsafe_policy_rag_include_records,
        f"unsafe_policy_rag_include_records={unsafe}; max={options.max_unsafe_policy_rag_include_records}.",
    )
    if options.min_source_trace_policy_A_records is not None:
        count = _int(report.get("source_trace_policy_A_records"))
        _add(
            checks,
            "stage4_source_trace_policy_A",
            count >= options.min_source_trace_policy_A_records,
            f"source_trace_policy_A_records={count}; minimum={options.min_source_trace_policy_A_records}.",
        )
    table_direct = _int(report.get("table_candidate_direct_rag_records"))
    _add(
        checks,
        "stage4_no_table_candidate_direct_rag",
        table_direct <= options.max_table_candidate_direct_rag_records,
        f"table_candidate_direct_rag_records={table_direct}; max={options.max_table_candidate_direct_rag_records}.",
    )
    visual_above = _int(report.get("visual_text_above_B_records"))
    _add(
        checks,
        "stage4_visual_text_conservative",
        visual_above <= options.max_visual_text_above_B_records,
        f"visual_text_above_B_records={visual_above}; max={options.max_visual_text_above_B_records}.",
    )

    summary = {
        "trace_lc_stage4_report_present": present,
        "trace_lc_stage4_status": report.get("status"),
        "trace_lc_stage4_version": report.get("version"),
        "trace_lc_stage4_records": report.get("records"),
        "trace_lc_stage4_pages": report.get("pages"),
        "trace_lc_stage4_policy_version": report.get("policy_version"),
        "trace_lc_stage4_policy_layers": report.get("policy_layers"),
        "trace_lc_stage4_policy_rag_include_records": report.get("policy_rag_include_records"),
        "trace_lc_stage4_trust_changed_records": report.get("trust_changed_records"),
        "trace_lc_stage4_rag_action_changed_records": report.get("rag_action_changed_records"),
        "trace_lc_stage4_repair_action_changed_records": report.get("repair_action_changed_records"),
        "trace_lc_stage4_unsafe_policy_rag_include_records": report.get("unsafe_policy_rag_include_records"),
        "trace_lc_stage4_source_trace_policy_A_records": report.get("source_trace_policy_A_records"),
        "trace_lc_stage4_table_candidate_direct_rag_records": report.get("table_candidate_direct_rag_records"),
        "trace_lc_stage4_visual_text_above_B_records": report.get("visual_text_above_B_records"),
        "trace_lc_stage4_policy_trust_tier_counts": report.get("policy_trust_tier_counts"),
        "trace_lc_stage4_policy_rag_action_counts": report.get("policy_rag_action_counts"),
        "trace_lc_stage4_eval_path": str(eval_path),
    }
    status = "OK" if all(check.ok for check in checks) else "FAIL"
    return Stage4QualityReport(status=status, summary=summary, checks=checks)


def write_stage4_quality(
    quality_path: Path = DEFAULT_QUALITY,
    eval_path: Path = DEFAULT_OUTPUT_JSON,
    options: Stage4QualityOptions | None = None,
) -> Stage4QualityReport:
    report = build_stage4_quality(eval_path, options)
    _write_json(quality_path, report.to_json())
    return report


def _print_report(report: Stage4QualityReport, quality_path: Path) -> None:
    print("TRACE-Net Layer Confidence Stage 4 policy simulation quality gate")
    print(f"  Status: {report.status}")
    print("  Summary:")
    for key, value in report.summary.items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in report.checks:
        label = "OK" if check.ok else "FAIL"
        print(f"    {label} {check.name}: {check.message}")
    print(f"\nJSON: {quality_path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Stage 4 policy simulation")
    parser.add_argument("--eval", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--quality", type=Path, default=DEFAULT_QUALITY)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-layers", type=int, default=6)
    parser.add_argument("--max-unsafe-policy-rag-include-records", type=int, default=0)
    parser.add_argument("--min-source-trace-policy-A-records", type=int, default=None)
    parser.add_argument("--max-table-candidate-direct-rag-records", type=int, default=0)
    parser.add_argument("--max-visual-text-above-B-records", type=int, default=0)
    parser.add_argument("--no-require-policy-present", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    options = Stage4QualityOptions(
        min_records=args.min_records,
        min_pages=args.min_pages,
        min_layers=args.min_layers,
        max_unsafe_policy_rag_include_records=args.max_unsafe_policy_rag_include_records,
        min_source_trace_policy_A_records=args.min_source_trace_policy_A_records,
        max_table_candidate_direct_rag_records=args.max_table_candidate_direct_rag_records,
        max_visual_text_above_B_records=args.max_visual_text_above_B_records,
        require_policy_present=not args.no_require_policy_present,
    )
    report = build_stage4_quality(args.eval, options)
    if args.write_json:
        _write_json(args.quality, report.to_json())
    _print_report(report, args.quality)
    return 0 if report.status == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
