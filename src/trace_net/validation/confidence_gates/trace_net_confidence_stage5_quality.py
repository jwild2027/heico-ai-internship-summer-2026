"""Quality gate for TRACE-Net Layer Confidence Stage 5b policy control."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_CONFIDENCE_DIR = Path("local_data/organization/trace_net/confidence/stage5_control")
DEFAULT_CONTROL_JSON = DEFAULT_CONFIDENCE_DIR / "trace_lc_stage5_policy_control_summary.json"
DEFAULT_CONTROL_RECORDS = DEFAULT_CONFIDENCE_DIR / "trace_lc_stage5_policy_control_records.jsonl"
DEFAULT_QUALITY = DEFAULT_CONFIDENCE_DIR / "trace_lc_stage5_policy_control_quality.json"


@dataclass(frozen=True)
class ConfidenceStage5QualityPaths:
    control_json: Path = DEFAULT_CONTROL_JSON
    control_records: Path = DEFAULT_CONTROL_RECORDS
    quality_path: Path = DEFAULT_QUALITY


@dataclass
class ConfidenceStage5QualityOptions:
    min_records: int = 1
    min_pages: int = 1
    min_policy_controlled_records: int = 1
    require_controlled_layers: tuple[str, ...] = ("source_trace", "part_catalog", "table_tile_text_refined")
    max_unsafe_final_rag_include_records: int = 0
    min_source_trace_final_A_records: int | None = None
    min_part_catalog_final_A_records: int | None = None
    max_controlled_routing_changed_records: int | None = None
    max_table_candidate_direct_rag_records: int = 0
    max_visual_text_controlled_records: int = 0
    min_table_tile_text_refined_controlled_records: int | None = None
    min_table_tile_text_refined_derived_context_records: int | None = None
    max_table_tile_text_refined_direct_verified_records: int = 0
    write_json: bool = False


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def run_confidence_stage5_quality(paths: ConfidenceStage5QualityPaths, options: ConfidenceStage5QualityOptions | None = None) -> dict[str, Any]:
    options = options or ConfidenceStage5QualityOptions()
    summary = _read_json(paths.control_json, {})
    summary = dict(summary) if isinstance(summary, Mapping) else {}
    records_count = _read_jsonl_count(paths.control_records)
    controlled_layers = set(summary.get("controlled_layers") or [])

    policy_controlled = int(summary.get("policy_controlled_records") if summary.get("policy_controlled_records") is not None else summary.get("controlled_records") or 0)
    unsafe = int(summary.get("unsafe_final_rag_include_records") if summary.get("unsafe_final_rag_include_records") is not None else summary.get("unsafe_stage5_rag_include_records") or 0)
    source_a = int(summary.get("source_trace_final_A_records") if summary.get("source_trace_final_A_records") is not None else summary.get("source_trace_policy_A_records") or 0)
    part_a = int(summary.get("part_catalog_final_A_records") if summary.get("part_catalog_final_A_records") is not None else summary.get("part_catalog_policy_A_records") or 0)
    table_direct = int(summary.get("table_candidate_direct_rag_records") or 0)
    visual_controlled = int(summary.get("visual_text_controlled_records") or 0)
    table_tile_text_controlled = int(summary.get("table_tile_text_refined_controlled_records") or 0)
    table_tile_text_derived = int(summary.get("table_tile_text_refined_derived_context_records") or 0)
    table_tile_text_direct_verified = int(summary.get("table_tile_text_refined_direct_verified_records") or 0)
    routing_changed = int(summary.get("controlled_routing_changed_records") or 0)

    checks: list[dict[str, Any]] = []
    checks.append(_check("stage5_artifacts_present", paths.control_json.exists() and paths.control_records.exists(), f"summary={paths.control_json.exists()}; records={paths.control_records.exists()}"))
    checks.append(_check("stage5_status", summary.get("status") == "OK", f"status={summary.get('status')!r}"))
    checks.append(_check("stage5_records", int(summary.get("records") or 0) >= options.min_records and records_count >= options.min_records, f"records summary={summary.get('records')}; jsonl={records_count}; minimum={options.min_records}"))
    checks.append(_check("stage5_pages", int(summary.get("pages") or 0) >= options.min_pages, f"pages={summary.get('pages')}; minimum={options.min_pages}"))
    checks.append(_check("stage5_policy_controlled_records", policy_controlled >= options.min_policy_controlled_records, f"policy_controlled_records={policy_controlled}; minimum={options.min_policy_controlled_records}"))
    missing_layers = sorted(set(options.require_controlled_layers) - controlled_layers)
    checks.append(_check("stage5_required_controlled_layers", not missing_layers, f"controlled_layers={sorted(controlled_layers)}; missing={missing_layers}"))
    checks.append(_check("stage5_no_unsafe_final_rag", unsafe <= options.max_unsafe_final_rag_include_records, f"unsafe_final_rag_include_records={unsafe}; max={options.max_unsafe_final_rag_include_records}"))
    if options.min_source_trace_final_A_records is not None:
        checks.append(_check("stage5_source_trace_final_A", source_a >= options.min_source_trace_final_A_records, f"source_trace_final_A_records={source_a}; minimum={options.min_source_trace_final_A_records}"))
    if options.min_part_catalog_final_A_records is not None:
        checks.append(_check("stage5_part_catalog_final_A", part_a >= options.min_part_catalog_final_A_records, f"part_catalog_final_A_records={part_a}; minimum={options.min_part_catalog_final_A_records}"))
    if options.max_controlled_routing_changed_records is not None:
        checks.append(_check("stage5_controlled_routing_changed", routing_changed <= options.max_controlled_routing_changed_records, f"controlled_routing_changed_records={routing_changed}; max={options.max_controlled_routing_changed_records}"))
    checks.append(_check("stage5_no_table_candidate_direct_rag", table_direct <= options.max_table_candidate_direct_rag_records, f"table_candidate_direct_rag_records={table_direct}; max={options.max_table_candidate_direct_rag_records}"))
    checks.append(_check("stage5_visual_text_not_controlled", visual_controlled <= options.max_visual_text_controlled_records, f"visual_text_controlled_records={visual_controlled}; max={options.max_visual_text_controlled_records}"))
    if options.min_table_tile_text_refined_controlled_records is not None:
        checks.append(_check("stage5_table_tile_text_refined_controlled", table_tile_text_controlled >= options.min_table_tile_text_refined_controlled_records, f"table_tile_text_refined_controlled_records={table_tile_text_controlled}; minimum={options.min_table_tile_text_refined_controlled_records}"))
    if options.min_table_tile_text_refined_derived_context_records is not None:
        checks.append(_check("stage5_table_tile_text_refined_derived_context", table_tile_text_derived >= options.min_table_tile_text_refined_derived_context_records, f"table_tile_text_refined_derived_context_records={table_tile_text_derived}; minimum={options.min_table_tile_text_refined_derived_context_records}"))
    checks.append(_check("stage5_table_tile_text_refined_not_direct_verified", table_tile_text_direct_verified <= options.max_table_tile_text_refined_direct_verified_records, f"table_tile_text_refined_direct_verified_records={table_tile_text_direct_verified}; max={options.max_table_tile_text_refined_direct_verified_records}"))

    status = "OK" if all(c["ok"] for c in checks) else "FAIL"
    result = {
        "status": status,
        "summary_present": paths.control_json.exists(),
        "records_present": paths.control_records.exists(),
        "stage5_status": summary.get("status"),
        "stage5_version": summary.get("version"),
        "stage5_records": summary.get("records"),
        "stage5_jsonl_records": records_count,
        "stage5_pages": summary.get("pages"),
        "stage5_controlled_layers": summary.get("controlled_layers"),
        "stage5_policy_controlled_records": policy_controlled,
        "stage5_rule_controlled_records": summary.get("rule_controlled_records"),
        "stage5_unsafe_final_rag_include_records": unsafe,
        "stage5_source_trace_final_A_records": source_a,
        "stage5_part_catalog_final_A_records": part_a,
        "stage5_table_candidate_direct_rag_records": table_direct,
        "stage5_visual_text_controlled_records": visual_controlled,
        "stage5_table_tile_text_refined_controlled_records": table_tile_text_controlled,
        "stage5_table_tile_text_refined_derived_context_records": table_tile_text_derived,
        "stage5_table_tile_text_refined_direct_verified_records": table_tile_text_direct_verified,
        "stage5_recommendation": summary.get("recommendation"),
        "checks": checks,
        "control_json_path": str(paths.control_json),
        "control_records_path": str(paths.control_records),
    }
    if options.write_json:
        paths.quality_path.parent.mkdir(parents=True, exist_ok=True)
        paths.quality_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Layer Confidence Stage 5b policy control quality.")
    parser.add_argument("--summary", "--control-json", dest="control_json", type=Path, default=DEFAULT_CONTROL_JSON)
    parser.add_argument("--records", "--control-records", dest="control_records", type=Path, default=DEFAULT_CONTROL_RECORDS)
    parser.add_argument("--quality", dest="quality_path", type=Path, default=DEFAULT_QUALITY)
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-controlled-records", "--min-policy-controlled-records", dest="min_policy_controlled_records", type=int, default=1)
    parser.add_argument("--min-source-trace-policy-A-records", "--min-source-trace-final-A-records", dest="min_source_trace_final_A_records", type=int, default=None)
    parser.add_argument("--min-part-catalog-policy-A-records", "--min-part-catalog-final-A-records", dest="min_part_catalog_final_A_records", type=int, default=None)
    parser.add_argument("--max-unsafe-stage5-rag-include-records", "--max-unsafe-final-rag-include-records", dest="max_unsafe_final_rag_include_records", type=int, default=0)
    parser.add_argument("--max-table-candidate-direct-rag-records", type=int, default=0)
    parser.add_argument("--max-visual-text-controlled-records", type=int, default=0)
    parser.add_argument("--min-table-tile-text-refined-controlled-records", type=int, default=None)
    parser.add_argument("--min-table-tile-text-refined-derived-context-records", type=int, default=None)
    parser.add_argument("--max-table-tile-text-refined-direct-verified-records", type=int, default=0)
    parser.add_argument("--max-controlled-routing-changed-records", type=int, default=None)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    result = run_confidence_stage5_quality(
        ConfidenceStage5QualityPaths(control_json=args.control_json, control_records=args.control_records, quality_path=args.quality_path),
        ConfidenceStage5QualityOptions(
            min_records=args.min_records,
            min_pages=args.min_pages,
            min_policy_controlled_records=args.min_policy_controlled_records,
            min_source_trace_final_A_records=args.min_source_trace_final_A_records,
            min_part_catalog_final_A_records=args.min_part_catalog_final_A_records,
            max_unsafe_final_rag_include_records=args.max_unsafe_final_rag_include_records,
            max_table_candidate_direct_rag_records=args.max_table_candidate_direct_rag_records,
            max_visual_text_controlled_records=args.max_visual_text_controlled_records,
            min_table_tile_text_refined_controlled_records=args.min_table_tile_text_refined_controlled_records,
            min_table_tile_text_refined_derived_context_records=args.min_table_tile_text_refined_derived_context_records,
            max_table_tile_text_refined_direct_verified_records=args.max_table_tile_text_refined_direct_verified_records,
            max_controlled_routing_changed_records=args.max_controlled_routing_changed_records,
            write_json=args.write_json,
        ),
    )
    print("TRACE-Net Layer Confidence Stage 5b quality gate")
    print(f"  Status: {result['status']}")
    print("  Summary:")
    for key in (
        "stage5_records", "stage5_pages", "stage5_controlled_layers", "stage5_policy_controlled_records",
        "stage5_unsafe_final_rag_include_records", "stage5_source_trace_final_A_records",
        "stage5_part_catalog_final_A_records", "stage5_table_candidate_direct_rag_records",
        "stage5_visual_text_controlled_records", "stage5_table_tile_text_refined_controlled_records",
        "stage5_table_tile_text_refined_derived_context_records", "stage5_recommendation",
    ):
        print(f"    {key}: {result.get(key)}")
    print("  Checks:")
    for check in result["checks"]:
        print(f"    {'OK' if check['ok'] else 'FAIL'} {check['name']}: {check['detail']}")
    if args.write_json:
        print(f"\nJSON: {args.quality_path}")
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())

# Backwards-compatible function name used by some local tests.
evaluate_confidence_stage5_quality = run_confidence_stage5_quality
