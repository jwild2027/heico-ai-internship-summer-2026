#!/usr/bin/env python
"""Check the latest TIFF backend pipeline manifest against quality gates."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import webbrowser

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.pipeline_quality import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    QualityGateThresholds,
    check_pipeline_manifest_file,
    format_quality_gate_result,
    write_quality_gate_html,
    write_quality_gate_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output-dir", default="local_data/pipeline_runs")
    parser.add_argument("--max-eval-failures", type=int, default=0)
    parser.add_argument("--max-manual-review", type=int, default=1)
    parser.add_argument("--max-qa-review", type=int, default=250)
    parser.add_argument("--max-suspicious-part-ata", type=int, default=10)
    parser.add_argument("--max-source-pages-without-links", type=int, default=0)
    parser.add_argument("--max-missing-source-tiff-files", type=int, default=0)
    parser.add_argument("--max-missing-source-ocr-files", type=int, default=0)
    parser.add_argument("--max-missing-source-urls", type=int, default=0)
    parser.add_argument("--max-source-sample-misses", type=int, default=0)
    parser.add_argument("--max-missing-ocr-paths", type=int, default=0)
    parser.add_argument("--max-missing-ocr-files", type=int, default=0)
    parser.add_argument("--max-unreadable-ocr-files", type=int, default=0)
    parser.add_argument("--max-empty-ocr-files", type=int, default=0)
    parser.add_argument("--max-short-ocr-files", type=int, default=0)
    parser.add_argument("--max-org-pages-without-ata", type=int, default=0)
    parser.add_argument("--min-org-distinct-parts", type=int, default=1)
    parser.add_argument("--min-org-part-mentions", type=int, default=1)
    parser.add_argument("--min-org-export-files", type=int, default=5)
    parser.add_argument(
        "--require-complete-ocr-text",
        action="store_true",
        help="Fail on empty/short OCR files. Keep off until blank/separator pages have been reviewed.",
    )
    parser.add_argument(
        "--require-real-rescarta",
        action="store_true",
        help="Fail unless ResCarta URLs are real non-local deep links. Keep off until the company URL format is known.",
    )
    parser.add_argument(
        "--require-incremental-smoke",
        action="store_true",
        help="Fail unless a passing changed-page incremental smoke-test summary is present in the manifest.",
    )
    parser.add_argument(
        "--no-require-graph-quality",
        action="store_true",
        help="Do not fail when graph/context quality artifacts are missing.",
    )
    parser.add_argument(
        "--require-user-query-tests",
        action="store_true",
        help="Fail unless scripts/run_user_query_tests.py results are present and all passing.",
    )
    parser.add_argument(
        "--require-realistic-query-trace",
        action="store_true",
        help="Fail unless scripts/run_realistic_query_trace_tests.py results are present and all passing.",
    )
    parser.add_argument(
        "--require-slow-realistic-query-trace",
        action="store_true",
        help="Fail unless the realistic query trace results include the slow LLM/RAG case.",
    )
    parser.add_argument("--max-graph-pages-without-context", type=int, default=0)
    parser.add_argument("--max-graph-pages-without-source-links", type=int, default=0)
    parser.add_argument("--max-graph-context-generation-errors", type=int, default=0)
    parser.add_argument("--strict", action="store_true", help="Compatibility flag; failures already return nonzero.")
    parser.add_argument("--write-html", action="store_true", help="Also write the legacy HTML quality report.")
    parser.add_argument("--open", action="store_true", help="Open the generated HTML quality report. Implies --write-html.")
    args = parser.parse_args()

    thresholds = QualityGateThresholds(
        max_eval_failures=args.max_eval_failures,
        max_manual_review=args.max_manual_review,
        max_qa_review=args.max_qa_review,
        max_suspicious_part_ata=args.max_suspicious_part_ata,
        max_source_pages_without_links=args.max_source_pages_without_links,
        max_missing_source_tiff_files=args.max_missing_source_tiff_files,
        max_missing_source_ocr_files=args.max_missing_source_ocr_files,
        max_missing_source_urls=args.max_missing_source_urls,
        max_source_sample_queries_without_results=args.max_source_sample_misses,
        max_missing_ocr_paths=args.max_missing_ocr_paths,
        max_missing_ocr_files=args.max_missing_ocr_files,
        max_unreadable_ocr_files=args.max_unreadable_ocr_files,
        max_empty_ocr_files=args.max_empty_ocr_files,
        max_short_ocr_files=args.max_short_ocr_files,
        max_org_pages_without_ata=args.max_org_pages_without_ata,
        min_org_distinct_parts=args.min_org_distinct_parts,
        min_org_part_mentions=args.min_org_part_mentions,
        min_org_export_files=args.min_org_export_files,
        require_complete_ocr_text=args.require_complete_ocr_text,
        require_real_rescarta=args.require_real_rescarta,
        require_incremental_smoke=args.require_incremental_smoke,
        require_graph_quality=not args.no_require_graph_quality,
        require_user_query_tests=args.require_user_query_tests,
        require_realistic_query_trace=args.require_realistic_query_trace,
        require_slow_realistic_query_trace=args.require_slow_realistic_query_trace,
        max_graph_pages_without_context=args.max_graph_pages_without_context,
        max_graph_pages_without_source_links=args.max_graph_pages_without_source_links,
        max_graph_context_generation_errors=args.max_graph_context_generation_errors,
    )
    result = check_pipeline_manifest_file(args.manifest, thresholds=thresholds)
    output_dir = Path(args.output_dir)
    json_path = write_quality_gate_json(result, output_dir / "latest_quality_gate.json")

    print(format_quality_gate_result(result))
    print(f"\nQuality JSON: {json_path}")

    if args.open:
        args.write_html = True
    if args.write_html:
        html_path = write_quality_gate_html(result, output_dir / "latest_quality_gate.html")
        print(f"Quality HTML: {html_path}")
        if args.open:
            webbrowser.open(html_path.resolve().as_uri())

    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
