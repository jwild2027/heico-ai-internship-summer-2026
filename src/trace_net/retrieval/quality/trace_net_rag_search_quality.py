"""Quality gate for TRACE-Net local RAG candidate search results."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_rag_search import DEFAULT_OUTPUT_DIR, QUALITY_FILE, RESULTS_FILE, RESULTS_JSONL_FILE, SUMMARY_FILE, SAFE_RAG_ACTIONS


@dataclass(frozen=True)
class RagSearchQualityPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    summary_path: Path | None = None
    results_path: Path | None = None
    results_jsonl_path: Path | None = None
    quality_path: Path | None = None

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / SUMMARY_FILE)

    @property
    def results(self) -> Path:
        return self.results_path or (self.output_dir / RESULTS_FILE)

    @property
    def results_jsonl(self) -> Path:
        return self.results_jsonl_path or (self.output_dir / RESULTS_JSONL_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / QUALITY_FILE)


@dataclass(frozen=True)
class RagSearchQualityOptions:
    min_results: int = 1
    min_searched_records: int = 1
    max_unsafe_results: int = 0
    max_excluded_results: int = 0
    min_source_results: int = 0
    min_source_text_results: int = 0
    min_verified_part_results: int = 0
    min_derived_results: int = 0
    require_status_ok: bool = True
    write_json: bool = False


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, Mapping):
                rows.append(dict(row))
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _check(ok: bool, name: str, message: str) -> dict[str, Any]:
    return {"ok": bool(ok), "name": name, "message": message}


def evaluate_search_quality(paths: RagSearchQualityPaths, options: RagSearchQualityOptions | None = None) -> dict[str, Any]:
    options = options or RagSearchQualityOptions()
    summary = _as_dict(_read_json(paths.summary, {}) or {})
    results_payload = _read_json(paths.results, {}) or {}
    results_json = _as_dict(results_payload).get("results") if isinstance(results_payload, Mapping) else None
    results = results_json if isinstance(results_json, list) else _read_jsonl(paths.results_jsonl)

    bucket_counts = _as_dict(summary.get("bucket_counts"))
    result_records = int(summary.get("result_records") or len(results))
    searched_records = int(summary.get("searched_records") or 0)
    unsafe_summary = int(summary.get("unsafe_result_records") or 0)
    unsafe_scan = len([row for row in results if not row.get("safe_candidate")])
    excluded_summary = int(summary.get("excluded_result_records") or 0)
    excluded_scan = len([row for row in results if row.get("final_rag_action") not in SAFE_RAG_ACTIONS])

    quality_summary = {
        "trace_net_search_summary_present": paths.summary.exists(),
        "trace_net_search_results_present": paths.results.exists() or paths.results_jsonl.exists(),
        "trace_net_search_status": summary.get("status"),
        "trace_net_search_query": summary.get("query"),
        "trace_net_search_effective_query": summary.get("effective_query"),
        "trace_net_search_candidate_records": summary.get("candidate_records"),
        "trace_net_search_safe_candidate_records": summary.get("safe_candidate_records"),
        "trace_net_search_searched_records": searched_records,
        "trace_net_search_result_records": result_records,
        "trace_net_search_jsonl_records": len(results),
        "trace_net_search_pages_found": summary.get("pages_found"),
        "trace_net_search_top_score": summary.get("top_score"),
        "trace_net_search_bucket_counts": bucket_counts,
        "trace_net_search_source_results": int(bucket_counts.get("source_evidence", 0)),
        "trace_net_search_source_text_results": int(bucket_counts.get("source_text_evidence", 0)),
        "trace_net_search_verified_part_results": int(bucket_counts.get("verified_part_evidence", 0)),
        "trace_net_search_derived_results": int(bucket_counts.get("derived_context", 0)),
        "trace_net_search_unsafe_results": max(unsafe_summary, unsafe_scan),
        "trace_net_search_excluded_results": max(excluded_summary, excluded_scan),
        "trace_net_search_results_path": str(paths.results),
        "trace_net_search_summary_path": str(paths.summary),
    }

    checks = [
        _check(paths.summary.exists() and (paths.results.exists() or paths.results_jsonl.exists()), "artifacts_present", f"summary={paths.summary.exists()}; results={paths.results.exists() or paths.results_jsonl.exists()}"),
        _check((not options.require_status_ok) or summary.get("status") == "OK", "status_ok", f"status={summary.get('status')} require_status_ok={options.require_status_ok}"),
        _check(result_records >= options.min_results, "result_records", f"results={result_records}; minimum={options.min_results}"),
        _check(len(results) == result_records, "result_count_match", f"summary={result_records}; json/jsonl={len(results)}"),
        _check(searched_records >= options.min_searched_records, "searched_records", f"searched_records={searched_records}; minimum={options.min_searched_records}"),
        _check(max(unsafe_summary, unsafe_scan) <= options.max_unsafe_results, "unsafe_results", f"unsafe_results summary={unsafe_summary}; scan={unsafe_scan}; max={options.max_unsafe_results}"),
        _check(max(excluded_summary, excluded_scan) <= options.max_excluded_results, "excluded_results", f"excluded_results summary={excluded_summary}; scan={excluded_scan}; max={options.max_excluded_results}"),
        _check(int(bucket_counts.get("source_evidence", 0)) >= options.min_source_results, "source_results", f"source_results={bucket_counts.get('source_evidence',0)}; minimum={options.min_source_results}"),
        _check(int(bucket_counts.get("source_text_evidence", 0)) >= options.min_source_text_results, "source_text_results", f"source_text_results={bucket_counts.get('source_text_evidence',0)}; minimum={options.min_source_text_results}"),
        _check(int(bucket_counts.get("verified_part_evidence", 0)) >= options.min_verified_part_results, "verified_part_results", f"verified_part_results={bucket_counts.get('verified_part_evidence',0)}; minimum={options.min_verified_part_results}"),
        _check(int(bucket_counts.get("derived_context", 0)) >= options.min_derived_results, "derived_results", f"derived_results={bucket_counts.get('derived_context',0)}; minimum={options.min_derived_results}"),
    ]
    status = "OK" if all(check["ok"] for check in checks) else "FAIL"
    report = {"status": status, "summary": quality_summary, "checks": checks}
    if options.write_json:
        _write_json(paths.quality, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net local RAG search quality.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--results", type=Path, default=None)
    parser.add_argument("--results-jsonl", type=Path, default=None)
    parser.add_argument("--quality", type=Path, default=None)
    parser.add_argument("--min-results", type=int, default=1)
    parser.add_argument("--min-searched-records", type=int, default=1)
    parser.add_argument("--max-unsafe-results", type=int, default=0)
    parser.add_argument("--max-excluded-results", type=int, default=0)
    parser.add_argument("--min-source-results", type=int, default=0)
    parser.add_argument("--min-source-text-results", type=int, default=0)
    parser.add_argument("--min-verified-part-results", type=int, default=0)
    parser.add_argument("--min-derived-results", type=int, default=0)
    parser.add_argument("--no-require-status-ok", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    paths = RagSearchQualityPaths(
        output_dir=args.output_dir,
        summary_path=args.summary,
        results_path=args.results,
        results_jsonl_path=args.results_jsonl,
        quality_path=args.quality,
    )
    options = RagSearchQualityOptions(
        min_results=args.min_results,
        min_searched_records=args.min_searched_records,
        max_unsafe_results=args.max_unsafe_results,
        max_excluded_results=args.max_excluded_results,
        min_source_results=args.min_source_results,
        min_source_text_results=args.min_source_text_results,
        min_verified_part_results=args.min_verified_part_results,
        min_derived_results=args.min_derived_results,
        require_status_ok=not args.no_require_status_ok,
        write_json=args.write_json,
    )
    report = evaluate_search_quality(paths, options)
    print("TRACE-Net local RAG search quality gate")
    print(f"  Status: {report['status']}")
    print("  Summary:")
    for key, value in report.get("summary", {}).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in report.get("checks", []):
        prefix = "OK" if check.get("ok") else "FAIL"
        print(f"    {prefix} {check.get('name')}: {check.get('message')}")
    if args.write_json:
        print(f"\nJSON: {paths.quality}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
