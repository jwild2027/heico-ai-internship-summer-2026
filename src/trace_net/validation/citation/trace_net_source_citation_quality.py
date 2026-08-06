"""Quality gate for TRACE-Net source citation formatter v1."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_source_citations import DEFAULT_OUTPUT_DIR, CITATION_RECORDS_FILE, SEARCH_CITATION_RECORDS_FILE, SUMMARY_FILE, QUALITY_FILE


@dataclass(frozen=True)
class SourceCitationQualityPaths:
    output_dir: Path = DEFAULT_OUTPUT_DIR
    summary_path: Path | None = None
    citations_path: Path | None = None
    search_citations_path: Path | None = None
    quality_path: Path | None = None

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / SUMMARY_FILE)

    @property
    def citations(self) -> Path:
        return self.citations_path or (self.output_dir / CITATION_RECORDS_FILE)

    @property
    def search_citations(self) -> Path:
        return self.search_citations_path or (self.output_dir / SEARCH_CITATION_RECORDS_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / QUALITY_FILE)


@dataclass(frozen=True)
class SourceCitationQualityOptions:
    min_candidate_citations: int = 1
    min_pages: int = 1
    min_complete_citations: int = 1
    min_search_citations: int = 0
    max_incomplete_citations: int | None = None
    max_unsafe_citations: int = 0
    max_empty_formatted: int = 0
    write_json: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _check(name: str, ok: bool, message: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "message": message}


def evaluate_source_citation_quality(paths: SourceCitationQualityPaths, options: SourceCitationQualityOptions | None = None) -> dict[str, Any]:
    options = options or SourceCitationQualityOptions()
    summary = _read_json(paths.summary, {}) or {}
    citations = _read_jsonl(paths.citations)
    search_citations = _read_jsonl(paths.search_citations)
    all_rows = [*citations, *search_citations]
    incomplete_scan = [row for row in all_rows if not row.get("citation_complete")]
    unsafe_scan = [row for row in all_rows if not row.get("safe_record")]
    empty_scan = [row for row in all_rows if not str(row.get("formatted_short") or "").strip() or not str(row.get("formatted_markdown") or "").strip()]
    pages = {str(row.get("page_id") or "") for row in all_rows if str(row.get("page_id") or "").strip()}

    report_summary = {
        "source_citation_summary_present": paths.summary.exists(),
        "source_citation_records_present": paths.citations.exists(),
        "source_citation_search_records_present": paths.search_citations.exists(),
        "source_citation_status": summary.get("status"),
        "source_citation_candidate_records": summary.get("candidate_citation_records", len(citations)),
        "source_citation_candidate_jsonl_records": len(citations),
        "source_citation_search_records": summary.get("search_result_citation_records", len(search_citations)),
        "source_citation_search_jsonl_records": len(search_citations),
        "source_citation_total_records": summary.get("citation_records_total", len(all_rows)),
        "source_citation_pages": summary.get("pages", len(pages)),
        "source_citation_complete_records": summary.get("complete_citation_records"),
        "source_citation_incomplete_records": summary.get("incomplete_citation_records"),
        "source_citation_incomplete_record_scan": len(incomplete_scan),
        "source_citation_unsafe_records": summary.get("unsafe_citation_records"),
        "source_citation_unsafe_record_scan": len(unsafe_scan),
        "source_citation_empty_formatted_records": summary.get("empty_formatted_records"),
        "source_citation_empty_formatted_scan": len(empty_scan),
        "source_citation_summary_path": str(paths.summary),
        "source_citation_records_path": str(paths.citations),
        "source_citation_search_records_path": str(paths.search_citations),
    }
    checks: list[dict[str, Any]] = []
    checks.append(_check("artifacts_present", paths.summary.exists() and paths.citations.exists(), f"summary={paths.summary.exists()}; citations={paths.citations.exists()}"))
    checks.append(_check("status_ok", summary.get("status") == "OK", f"status={summary.get('status')}"))
    checks.append(_check("candidate_citations", len(citations) >= options.min_candidate_citations, f"candidate citations={len(citations)}; minimum={options.min_candidate_citations}"))
    checks.append(_check("candidate_count_match", int(summary.get("candidate_citation_records") or len(citations)) == len(citations), f"summary={summary.get('candidate_citation_records')}; jsonl={len(citations)}"))
    checks.append(_check("pages", int(summary.get("pages") or len(pages)) >= options.min_pages, f"pages={summary.get('pages', len(pages))}; minimum={options.min_pages}"))
    checks.append(_check("complete_citations", int(summary.get("complete_citation_records") or 0) >= options.min_complete_citations, f"complete={summary.get('complete_citation_records')}; minimum={options.min_complete_citations}"))
    checks.append(_check("search_citations", len(search_citations) >= options.min_search_citations, f"search citations={len(search_citations)}; minimum={options.min_search_citations}"))
    if options.max_incomplete_citations is not None:
        checks.append(_check("incomplete_citations", len(incomplete_scan) <= options.max_incomplete_citations, f"incomplete scan={len(incomplete_scan)}; max={options.max_incomplete_citations}"))
    checks.append(_check("unsafe_citations", len(unsafe_scan) <= options.max_unsafe_citations, f"unsafe scan={len(unsafe_scan)}; max={options.max_unsafe_citations}"))
    checks.append(_check("empty_formatted", len(empty_scan) <= options.max_empty_formatted, f"empty formatted scan={len(empty_scan)}; max={options.max_empty_formatted}"))

    status = "OK" if all(check["ok"] for check in checks) else "FAIL"
    report = {
        "status": status,
        "version": "trace_net_source_citation_quality_v1",
        "created_at": _utc_now(),
        "summary": report_summary,
        "checks": checks,
    }
    if options.write_json:
        _write_json(paths.quality, report)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net source citation formatter quality.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--summary", default="")
    parser.add_argument("--citations", default="")
    parser.add_argument("--search-citations", default="")
    parser.add_argument("--quality", default="")
    parser.add_argument("--min-candidate-citations", type=int, default=1)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-complete-citations", type=int, default=1)
    parser.add_argument("--min-search-citations", type=int, default=0)
    parser.add_argument("--max-incomplete-citations", type=int, default=-1)
    parser.add_argument("--max-unsafe-citations", type=int, default=0)
    parser.add_argument("--max-empty-formatted", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = SourceCitationQualityPaths(
        output_dir=Path(args.output_dir),
        summary_path=Path(args.summary) if args.summary else None,
        citations_path=Path(args.citations) if args.citations else None,
        search_citations_path=Path(args.search_citations) if args.search_citations else None,
        quality_path=Path(args.quality) if args.quality else None,
    )
    options = SourceCitationQualityOptions(
        min_candidate_citations=args.min_candidate_citations,
        min_pages=args.min_pages,
        min_complete_citations=args.min_complete_citations,
        min_search_citations=args.min_search_citations,
        max_incomplete_citations=None if args.max_incomplete_citations < 0 else args.max_incomplete_citations,
        max_unsafe_citations=args.max_unsafe_citations,
        max_empty_formatted=args.max_empty_formatted,
        write_json=args.write_json,
    )
    report = evaluate_source_citation_quality(paths, options)
    print("TRACE-Net source citation quality gate")
    print(f"  Status: {report.get('status')}")
    print("  Summary:")
    for key, value in report.get("summary", {}).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in report.get("checks", []):
        prefix = "OK" if check.get("ok") else "FAIL"
        print(f"    {prefix} {check.get('name')}: {check.get('message')}")
    if options.write_json:
        print(f"\nJSON: {paths.quality}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
