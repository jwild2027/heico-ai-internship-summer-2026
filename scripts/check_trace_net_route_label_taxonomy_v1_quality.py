from pathlib import Path
import argparse
import json
import sys
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check_quality(
    *,
    report_path: Path,
    min_route_labels: int = 9,
    require_label: List[str] | None = None,
    require_legacy_alias: List[str] | None = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
    max_unsafe: int | None = None,
    write_json: bool = False,
) -> Dict[str, Any]:
    payload = _load(report_path)
    summary = payload.get("summary") or {}
    records = payload.get("records") or []
    labels = {record.get("label") for record in records}
    aliases = set((payload.get("legacy_route_aliases") or {}).keys())
    failures: List[str] = []

    if payload.get("quality_status") != "PASS":
        failures.append("manifest quality_status is not PASS")
    if len(records) < min_route_labels:
        failures.append(f"not enough route labels: {len(records)} < {min_route_labels}")
    for label in require_label or []:
        if label not in labels:
            failures.append(f"required label missing: {label}")
    for alias in require_legacy_alias or []:
        if alias not in aliases:
            failures.append(f"required legacy alias missing: {alias}")
    if require_no_answer_permission and summary.get("answer_permission_count", 0) != 0:
        failures.append("answer permission was present")
    if require_no_source_truth_mutation and summary.get("source_truth_mutation_allowed_count", 0) != 0:
        failures.append("source truth mutation was allowed")
    if require_no_write_attempts:
        for key in ["postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"]:
            if summary.get(key, 0) != 0:
                failures.append(f"{key} was non-zero")
    if max_unsafe is not None and summary.get("unsafe_record_count", 0) > max_unsafe:
        failures.append("too many unsafe records")

    result = {
        "quality_status": "PASS" if not failures else "FAIL",
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }
    if write_json:
        out = report_path.with_name("trace_net_route_label_taxonomy_v1_quality_check.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        result["wrote"] = str(out)
    return result


def main() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check TRACE-Net route label taxonomy quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-route-labels", type=int, default=9)
    parser.add_argument("--require-label", action="append", default=[])
    parser.add_argument("--require-legacy-alias", action="append", default=[])
    parser.add_argument("--max-unsafe", type=int)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args()

    result = check_quality(
        report_path=Path(args.report_path),
        min_route_labels=args.min_route_labels,
        require_label=args.require_label,
        require_legacy_alias=args.require_legacy_alias,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
        max_unsafe=args.max_unsafe,
        write_json=args.write_json,
    )
    print(f"Quality status: {result['quality_status']}")
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if result.get("wrote"):
        print("Wrote:", result["wrote"])
    if result["quality_status"] != "PASS":
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    main()
