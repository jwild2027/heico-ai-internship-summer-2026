"""Quality gate for TRACE-Net source citation formatting."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .trace_net_source_citations import (
    DEFAULT_OUTPUT_DIR,
    CITATIONS_FILE,
    CITATION_SUMMARY_FILE,
    QUALITY_FILE,
    _read_jsonl,
    _text,
    _as_dict,
    _write_json,
)


@dataclass(frozen=True)
class SourceCitationQualityPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    citations_path: Path | None = None
    summary_path: Path | None = None
    quality_path: Path | None = None

    @property
    def citations(self) -> Path:
        return self.citations_path or (self.output_dir / CITATIONS_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / CITATION_SUMMARY_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / QUALITY_FILE)


@dataclass(frozen=True)
class SourceCitationQualityOptions:
    min_citations: int = 1
    min_pages: int = 1
    min_source_traceable: int = 1
    min_search_results_with_citations: int = 0
    max_unsafe_citations: int = 0
    max_missing_source_url: int | None = 0
    max_missing_tiff_path: int | None = None
    max_missing_ocr_path: int | None = None
    write_json: bool = False


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _scan_citations(citations: list[dict[str, Any]]) -> dict[str, Any]:
    unsafe = []
    missing_source = []
    missing_tiff = []
    missing_ocr = []
    source_traceable = []
    pages = set()
    search_ready = []
    for row in citations:
        page_id = _text(row.get("page_id"))
        if page_id:
            pages.add(page_id)
        if not row.get("is_rag_safe") or _text(row.get("final_trust_tier")) == "D":
            unsafe.append(row)
        if not _text(row.get("source_url")):
            missing_source.append(row)
        if not _text(row.get("tiff_path")):
            missing_tiff.append(row)
        if not _text(row.get("ocr_path")):
            missing_ocr.append(row)
        if row.get("is_source_traceable"):
            source_traceable.append(row)
        if _text(row.get("citation_text")) and _text(row.get("citation_id")):
            search_ready.append(row)
    return {
        "scan_citation_records": len(citations),
        "scan_pages": len(pages),
        "scan_unsafe_citations": len(unsafe),
        "scan_missing_source_url": len(missing_source),
        "scan_missing_tiff_path": len(missing_tiff),
        "scan_missing_ocr_path": len(missing_ocr),
        "scan_source_traceable_records": len(source_traceable),
        "scan_citation_text_records": len(search_ready),
    }


def check_trace_net_source_citation_quality(paths: SourceCitationQualityPaths, options: SourceCitationQualityOptions | None = None) -> dict[str, Any]:
    options = options or SourceCitationQualityOptions()
    summary = _as_dict(_read_json(paths.summary, {}) or {})
    citations = _read_jsonl(paths.citations)
    scan = _scan_citations(citations)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    summary_present = paths.summary.exists()
    citations_present = paths.citations.exists()
    add("artifacts_present", summary_present and citations_present, f"summary={summary_present}; citations={citations_present}")
    add("status_ok", summary.get("status") == "OK", f"status={summary.get('status')}")
    citation_records = int(summary.get("citation_records") or scan["scan_citation_records"] or 0)
    add("citation_records", citation_records >= options.min_citations, f"citation_records={citation_records}; minimum={options.min_citations}")
    add("citation_record_count_match", citation_records == scan["scan_citation_records"], f"summary={citation_records}; jsonl={scan['scan_citation_records']}")
    pages = int(summary.get("pages") or scan["scan_pages"] or 0)
    add("pages", pages >= options.min_pages, f"pages={pages}; minimum={options.min_pages}")
    unsafe = int(summary.get("unsafe_citation_records") or scan["scan_unsafe_citations"] or 0)
    add("unsafe_citations", unsafe <= options.max_unsafe_citations, f"unsafe={unsafe}; max={options.max_unsafe_citations}")
    source_traceable = int(summary.get("source_traceable_records") or scan["scan_source_traceable_records"] or 0)
    add("source_traceable", source_traceable >= options.min_source_traceable, f"source_traceable={source_traceable}; minimum={options.min_source_traceable}")
    search_with = int(summary.get("search_results_with_citations") or 0)
    add("search_results_with_citations", search_with >= options.min_search_results_with_citations, f"search_results_with_citations={search_with}; minimum={options.min_search_results_with_citations}")
    missing_source = int(summary.get("missing_source_url_records") or scan["scan_missing_source_url"] or 0)
    if options.max_missing_source_url is not None:
        add("missing_source_url", missing_source <= options.max_missing_source_url, f"missing_source_url={missing_source}; max={options.max_missing_source_url}")
    missing_tiff = int(summary.get("missing_tiff_path_records") or scan["scan_missing_tiff_path"] or 0)
    if options.max_missing_tiff_path is not None:
        add("missing_tiff_path", missing_tiff <= options.max_missing_tiff_path, f"missing_tiff_path={missing_tiff}; max={options.max_missing_tiff_path}")
    missing_ocr = int(summary.get("missing_ocr_path_records") or scan["scan_missing_ocr_path"] or 0)
    if options.max_missing_ocr_path is not None:
        add("missing_ocr_path", missing_ocr <= options.max_missing_ocr_path, f"missing_ocr_path={missing_ocr}; max={options.max_missing_ocr_path}")
    citation_text_records = scan["scan_citation_text_records"]
    add("citation_text_records", citation_text_records == scan["scan_citation_records"], f"citation_text_records={citation_text_records}; citations={scan['scan_citation_records']}")

    status = "OK" if all(check["ok"] for check in checks) else "FAIL"
    report = {
        "status": status,
        "summary_path": str(paths.summary),
        "citations_path": str(paths.citations),
        "citation_summary_present": summary_present,
        "citation_records_present": citations_present,
        "citation_records": citation_records,
        "citation_jsonl_records": scan["scan_citation_records"],
        "citation_pages": pages,
        "citation_source_traceable_records": source_traceable,
        "citation_unsafe_records": unsafe,
        "citation_missing_source_url_records": missing_source,
        "citation_missing_tiff_path_records": missing_tiff,
        "citation_missing_ocr_path_records": missing_ocr,
        "citation_search_results_with_citations": search_with,
        "citation_bucket_counts": summary.get("rag_bucket_counts", {}),
        "citation_kind_counts": summary.get("citation_kind_counts", {}),
        "checks": checks,
    }
    if options.write_json:
        _write_json(paths.quality, report)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net source citation formatting quality.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--citations", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--quality", default="")
    parser.add_argument("--min-citations", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-source-traceable", type=int, default=1)
    parser.add_argument("--min-search-results-with-citations", type=int, default=0)
    parser.add_argument("--max-unsafe-citations", type=int, default=0)
    parser.add_argument("--max-missing-source-url", type=int, default=0)
    parser.add_argument("--max-missing-tiff-path", type=int, default=None)
    parser.add_argument("--max-missing-ocr-path", type=int, default=None)
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    paths = SourceCitationQualityPaths(
        output_dir=output_dir,
        citations_path=Path(args.citations) if args.citations else None,
        summary_path=Path(args.summary) if args.summary else None,
        quality_path=Path(args.quality) if args.quality else None,
    )
    options = SourceCitationQualityOptions(
        min_citations=max(0, int(args.min_citations or 0)),
        min_pages=max(0, int(args.min_pages or 0)),
        min_source_traceable=max(0, int(args.min_source_traceable or 0)),
        min_search_results_with_citations=max(0, int(args.min_search_results_with_citations or 0)),
        max_unsafe_citations=max(0, int(args.max_unsafe_citations or 0)),
        max_missing_source_url=args.max_missing_source_url,
        max_missing_tiff_path=args.max_missing_tiff_path,
        max_missing_ocr_path=args.max_missing_ocr_path,
        write_json=bool(args.write_json),
    )
    report = check_trace_net_source_citation_quality(paths, options)
    print("TRACE-Net source citation quality gate")
    print(f"  Status: {report.get('status')}")
    print("  Summary:")
    for key in (
        "citation_records", "citation_pages", "citation_source_traceable_records", "citation_unsafe_records",
        "citation_missing_source_url_records", "citation_missing_tiff_path_records", "citation_missing_ocr_path_records",
        "citation_search_results_with_citations",
    ):
        print(f"    {key}: {report.get(key)}")
    print("  Checks:")
    for check in report.get("checks", []):
        print(f"    {'OK' if check.get('ok') else 'FAIL'} {check.get('name')}: {check.get('detail')}")
    if options.write_json:
        print(f"\nJSON: {paths.quality}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
