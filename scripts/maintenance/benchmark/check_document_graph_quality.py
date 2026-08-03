#!/usr/bin/env python
"""Check document graph/context/source traceability quality."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.document_graph_quality import (  # noqa: E402
    DEFAULT_CONTEXT_FILE,
    DEFAULT_GRAPH_DIR,
    DEFAULT_GRAPH_QUALITY_JSON,
    DEFAULT_REALISTIC_QUERY_TRACE_RESULTS,
    DEFAULT_USER_QUERY_RESULTS,
    GraphQualityThresholds,
    build_graph_quality_result,
    format_graph_quality_result,
    write_graph_quality_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-dir", default=DEFAULT_GRAPH_DIR)
    parser.add_argument("--context-file", default=DEFAULT_CONTEXT_FILE)
    parser.add_argument("--user-query-results", default=DEFAULT_USER_QUERY_RESULTS)
    parser.add_argument("--realistic-query-results", default=DEFAULT_REALISTIC_QUERY_TRACE_RESULTS)
    parser.add_argument("--json-output", default=DEFAULT_GRAPH_QUALITY_JSON)
    parser.add_argument("--max-pages-without-context", type=int, default=0)
    parser.add_argument("--max-pages-without-source-links", type=int, default=0)
    parser.add_argument("--max-context-generation-errors", type=int, default=0)
    parser.add_argument("--require-user-query-tests", action="store_true")
    parser.add_argument("--require-realistic-query-trace", action="store_true")
    parser.add_argument("--require-slow-realistic-query-trace", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Compatibility flag; failures already return nonzero.")
    args = parser.parse_args()

    thresholds = GraphQualityThresholds(
        max_pages_without_context=args.max_pages_without_context,
        max_pages_without_source_links=args.max_pages_without_source_links,
        max_context_generation_errors=args.max_context_generation_errors,
        require_user_query_tests=args.require_user_query_tests,
        require_realistic_query_trace_tests=args.require_realistic_query_trace,
        require_slow_realistic_query_trace=args.require_slow_realistic_query_trace,
    )
    result = build_graph_quality_result(
        graph_dir=args.graph_dir,
        context_file=args.context_file,
        user_query_results=args.user_query_results,
        realistic_query_results=args.realistic_query_results,
        thresholds=thresholds,
    )
    print(format_graph_quality_result(result))
    if args.write_json:
        out = write_graph_quality_json(result, args.json_output)
        print(f"\nJSON: {out}")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
