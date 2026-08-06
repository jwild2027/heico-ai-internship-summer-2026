"""Quality checks for TRACE-Net search result grouper v1."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_search_grouper import (
    DEFAULT_OUTPUT_DIR,
    GROUPED_QUALITY_FILE,
    GROUPED_RESULTS_JSONL_FILE,
    GROUPED_SUMMARY_FILE,
    _read_json,
    _read_jsonl,
    _text,
    _write_json,
)


@dataclass(frozen=True)
class SearchGroupQualityPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    grouped_summary_path: Path | None = None
    grouped_results_jsonl_path: Path | None = None
    quality_path: Path | None = None

    @property
    def grouped_summary(self) -> Path:
        return self.grouped_summary_path or (self.output_dir / GROUPED_SUMMARY_FILE)

    @property
    def grouped_results_jsonl(self) -> Path:
        return self.grouped_results_jsonl_path or (self.output_dir / GROUPED_RESULTS_JSONL_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / GROUPED_QUALITY_FILE)


@dataclass(frozen=True)
class SearchGroupQualityOptions:
    min_groups: int = 1
    min_pages: int = 1
    min_supporting_results: int = 1
    min_groups_with_multiple_buckets: int = 0
    min_groups_with_citations: int = 0
    max_unsafe_groups: int = 0
    max_excluded_groups: int = 0
    max_missing_source_url_groups: int | None = None
    max_missing_tiff_path_groups: int | None = None
    max_missing_ocr_path_groups: int | None = None
    require_status_ok: bool = True
    write_json: bool = False


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def evaluate_search_group_quality(paths: SearchGroupQualityPaths, options: SearchGroupQualityOptions | None = None) -> dict[str, Any]:
    options = options or SearchGroupQualityOptions()
    summary = _read_json(paths.grouped_summary)
    groups = _read_jsonl(paths.grouped_results_jsonl)
    jsonl_count = len(groups)
    unsafe_scan = sum(1 for row in groups if not row.get("safe_group") or int(row.get("unsafe_supporting_results") or 0) > 0)
    excluded_scan = sum(1 for row in groups if int(row.get("excluded_supporting_results") or 0) > 0)
    missing_source_url_scan = sum(1 for row in groups if not _text(row.get("source_url")))
    missing_tiff_path_scan = sum(1 for row in groups if not _text(row.get("tiff_path")))
    missing_ocr_path_scan = sum(1 for row in groups if not _text(row.get("ocr_path")))
    supporting_scan = sum(int(row.get("supporting_result_count") or row.get("result_count") or 0) for row in groups)
    groups_with_support_scan = sum(1 for row in groups if int(row.get("supporting_result_count") or row.get("result_count") or 0) > 0)
    multiple_buckets_scan = sum(1 for row in groups if len(_as_list(row.get("rag_buckets"))) > 1)
    citations_scan = sum(1 for row in groups if int(row.get("citation_count") or 0) > 0)
    report_summary = {
        "search_group_summary_present": paths.grouped_summary.exists(),
        "search_group_results_present": paths.grouped_results_jsonl.exists(),
        "search_group_status": summary.get("status", "missing"),
        "search_group_version": summary.get("version", ""),
        "search_group_search_result_records": summary.get("search_result_records", 0),
        "search_group_grouped_page_records": summary.get("grouped_page_records", 0),
        "search_group_jsonl_records": jsonl_count,
        "search_group_pages_found": summary.get("pages_found", 0),
        "search_group_supporting_result_records": summary.get("supporting_result_records", 0),
        "search_group_supporting_result_records_scan": supporting_scan,
        "search_group_groups_with_support": groups_with_support_scan,
        "search_group_unsafe_grouped_records": summary.get("unsafe_grouped_records", 0),
        "search_group_unsafe_grouped_records_scan": unsafe_scan,
        "search_group_excluded_grouped_records": summary.get("excluded_grouped_records", 0),
        "search_group_excluded_grouped_records_scan": excluded_scan,
        "search_group_groups_with_multiple_buckets": summary.get("groups_with_multiple_buckets", 0),
        "search_group_groups_with_multiple_buckets_scan": multiple_buckets_scan,
        "search_group_groups_with_citations": summary.get("groups_with_citations", 0),
        "search_group_groups_with_citations_scan": citations_scan,
        "search_group_groups_with_source_url": summary.get("groups_with_source_url", 0),
        "search_group_groups_with_tiff_path": summary.get("groups_with_tiff_path", 0),
        "search_group_groups_with_ocr_path": summary.get("groups_with_ocr_path", 0),
        "search_group_missing_source_url_scan": missing_source_url_scan,
        "search_group_missing_tiff_path_scan": missing_tiff_path_scan,
        "search_group_missing_ocr_path_scan": missing_ocr_path_scan,
        "search_group_top_group_score": summary.get("top_group_score", 0),
        "search_group_summary_path": str(paths.grouped_summary),
        "search_group_results_path": str(paths.grouped_results_jsonl),
    }
    checks: list[dict[str, Any]] = []
    checks.append(_check("artifacts_present", paths.grouped_summary.exists() and paths.grouped_results_jsonl.exists(), f"summary={paths.grouped_summary.exists()}; grouped_jsonl={paths.grouped_results_jsonl.exists()}"))
    if options.require_status_ok:
        checks.append(_check("status_ok", summary.get("status") == "OK", f"status={summary.get('status')}"))
    grouped_count = int(summary.get("grouped_page_records") or 0)
    pages_found = int(summary.get("pages_found") or 0)
    checks.append(_check("grouped_records", grouped_count >= options.min_groups and jsonl_count >= options.min_groups, f"summary={grouped_count}; jsonl={jsonl_count}; minimum={options.min_groups}"))
    checks.append(_check("group_count_match", grouped_count == jsonl_count, f"summary={grouped_count}; jsonl={jsonl_count}"))
    checks.append(_check("pages", pages_found >= options.min_pages, f"pages_found={pages_found}; minimum={options.min_pages}"))
    checks.append(_check("supporting_results", supporting_scan >= options.min_supporting_results, f"supporting_results_scan={supporting_scan}; minimum={options.min_supporting_results}"))
    checks.append(_check("groups_have_support", groups_with_support_scan == jsonl_count, f"groups_with_support={groups_with_support_scan}; groups={jsonl_count}"))
    checks.append(_check("unsafe_groups", unsafe_scan <= options.max_unsafe_groups and int(summary.get("unsafe_grouped_records") or 0) <= options.max_unsafe_groups, f"unsafe summary={summary.get('unsafe_grouped_records')}; scan={unsafe_scan}; max={options.max_unsafe_groups}"))
    checks.append(_check("excluded_groups", excluded_scan <= options.max_excluded_groups and int(summary.get("excluded_grouped_records") or 0) <= options.max_excluded_groups, f"excluded summary={summary.get('excluded_grouped_records')}; scan={excluded_scan}; max={options.max_excluded_groups}"))
    checks.append(_check("groups_with_multiple_buckets", multiple_buckets_scan >= options.min_groups_with_multiple_buckets, f"multiple_bucket_groups={multiple_buckets_scan}; minimum={options.min_groups_with_multiple_buckets}"))
    checks.append(_check("groups_with_citations", citations_scan >= options.min_groups_with_citations, f"groups_with_citations={citations_scan}; minimum={options.min_groups_with_citations}"))
    if options.max_missing_source_url_groups is not None:
        checks.append(_check("missing_source_url", missing_source_url_scan <= options.max_missing_source_url_groups, f"missing_source_url_groups={missing_source_url_scan}; max={options.max_missing_source_url_groups}"))
    if options.max_missing_tiff_path_groups is not None:
        checks.append(_check("missing_tiff_path", missing_tiff_path_scan <= options.max_missing_tiff_path_groups, f"missing_tiff_path_groups={missing_tiff_path_scan}; max={options.max_missing_tiff_path_groups}"))
    if options.max_missing_ocr_path_groups is not None:
        checks.append(_check("missing_ocr_path", missing_ocr_path_scan <= options.max_missing_ocr_path_groups, f"missing_ocr_path_groups={missing_ocr_path_scan}; max={options.max_missing_ocr_path_groups}"))
    status = "OK" if all(check["ok"] for check in checks) else "FAIL"
    report = {"status": status, "summary": report_summary, "checks": checks}
    if options.write_json:
        _write_json(paths.quality, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net grouped search result quality.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--grouped-summary", type=Path, default=None)
    parser.add_argument("--grouped-results-jsonl", type=Path, default=None)
    parser.add_argument("--quality", type=Path, default=None)
    parser.add_argument("--min-groups", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-supporting-results", type=int, default=1)
    parser.add_argument("--min-groups-with-multiple-buckets", type=int, default=0)
    parser.add_argument("--min-groups-with-citations", type=int, default=0)
    parser.add_argument("--max-unsafe-groups", type=int, default=0)
    parser.add_argument("--max-excluded-groups", type=int, default=0)
    parser.add_argument("--max-missing-source-url-groups", type=int, default=None)
    parser.add_argument("--max-missing-tiff-path-groups", type=int, default=None)
    parser.add_argument("--max-missing-ocr-path-groups", type=int, default=None)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    paths = SearchGroupQualityPaths(output_dir=args.output_dir, grouped_summary_path=args.grouped_summary, grouped_results_jsonl_path=args.grouped_results_jsonl, quality_path=args.quality)
    options = SearchGroupQualityOptions(
        min_groups=args.min_groups,
        min_pages=args.min_pages,
        min_supporting_results=args.min_supporting_results,
        min_groups_with_multiple_buckets=args.min_groups_with_multiple_buckets,
        min_groups_with_citations=args.min_groups_with_citations,
        max_unsafe_groups=args.max_unsafe_groups,
        max_excluded_groups=args.max_excluded_groups,
        max_missing_source_url_groups=args.max_missing_source_url_groups,
        max_missing_tiff_path_groups=args.max_missing_tiff_path_groups,
        max_missing_ocr_path_groups=args.max_missing_ocr_path_groups,
        write_json=args.write_json,
    )
    result = evaluate_search_group_quality(paths, options)
    print("TRACE-Net grouped search quality gate")
    print(f"  Status: {result['status']}")
    print("  Summary:")
    for key, value in result.get("summary", {}).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in result.get("checks", []):
        label = "OK" if check.get("ok") else "FAIL"
        print(f"    {label} {check.get('name')}: {check.get('detail')}")
    if args.write_json:
        print(f"\nJSON: {paths.quality}")
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())

# Backwards-compatible helper used by unit tests and ad-hoc scripts.
def check_grouped_search_quality(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    min_groups: int = 1,
    min_pages: int = 1,
    min_supporting_results: int = 1,
    min_groups_with_citations: int = 0,
    min_groups_with_multiple_buckets: int = 0,
    min_groups_with_source_url: int = 0,
    max_unsafe_grouped_records: int = 0,
    max_excluded_grouped_records: int = 0,
    write_json_flag: bool = False,
) -> dict[str, Any]:
    paths = SearchGroupQualityPaths(output_dir=output_dir)
    result = evaluate_search_group_quality(
        paths,
        SearchGroupQualityOptions(
            min_groups=min_groups,
            min_pages=min_pages,
            min_supporting_results=min_supporting_results,
            min_groups_with_citations=min_groups_with_citations,
            min_groups_with_multiple_buckets=min_groups_with_multiple_buckets,
            max_unsafe_groups=max_unsafe_grouped_records,
            max_excluded_groups=max_excluded_grouped_records,
            write_json=write_json_flag,
        ),
    )
    flat = {"status": result.get("status")}
    flat.update(result.get("summary", {}))
    flat["grouped_page_records"] = flat.get("search_group_grouped_page_records", 0)
    flat["unsafe_grouped_records"] = flat.get("search_group_unsafe_grouped_records_scan", 0)
    flat["excluded_grouped_records"] = flat.get("search_group_excluded_grouped_records_scan", 0)
    flat["groups_with_source_url"] = int(flat.get("search_group_jsonl_records", 0)) - int(flat.get("search_group_missing_source_url_scan", 0))
    flat["groups_with_tiff_path"] = int(flat.get("search_group_jsonl_records", 0)) - int(flat.get("search_group_missing_tiff_path_scan", 0))
    flat["groups_with_ocr_path"] = int(flat.get("search_group_jsonl_records", 0)) - int(flat.get("search_group_missing_ocr_path_scan", 0))
    # Convenience graph counts, if files exist.
    graph_nodes_path = output_dir / "trace_net_search_grouped_graph_nodes.json"
    graph_edges_path = output_dir / "trace_net_search_grouped_graph_edges.json"
    try:
        flat["graph_nodes"] = len(json.loads(graph_nodes_path.read_text(encoding="utf-8"))) if graph_nodes_path.exists() else 0
    except Exception:
        flat["graph_nodes"] = 0
    try:
        flat["graph_edges"] = len(json.loads(graph_edges_path.read_text(encoding="utf-8"))) if graph_edges_path.exists() else 0
    except Exception:
        flat["graph_edges"] = 0
    if min_groups_with_source_url and flat["groups_with_source_url"] < min_groups_with_source_url:
        flat["status"] = "FAIL"
    return flat
