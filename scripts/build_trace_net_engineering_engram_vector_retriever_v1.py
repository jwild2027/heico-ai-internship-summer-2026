#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_engineering_engram_vector_retriever_v1 import build_vector_retriever_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Vector Retriever v1 artifact")
    p.add_argument("--vector-loader", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--queries-jsonl", default=None)
    p.add_argument("--query", action="append", default=None, help="Inline query text; may be repeated")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--min-queries", type=int, default=1)
    p.add_argument("--min-results-per-query", type=int, default=1)
    p.add_argument("--require-all-layers", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = build_vector_retriever_manifest(
        vector_loader_path=args.vector_loader,
        output_dir=args.output_dir,
        queries_path=args.queries_jsonl,
        inline_queries=args.query,
        top_k=args.top_k,
        min_queries=args.min_queries,
        min_results_per_query=args.min_results_per_query,
        require_all_layers=args.require_all_layers,
        max_unsafe=args.max_unsafe,
        max_write_attempts=args.max_write_attempts,
    )
    summary = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"query_count={summary.get('query_count')}")
    print(f"retrieval_record_count={summary.get('retrieval_record_count')}")
    print(f"total_retrieved_item_count={summary.get('total_retrieved_item_count')}")
    print(f"unsafe_finding_count={summary.get('unsafe_finding_count')}")
    print(f"answer_permission_count={summary.get('answer_permission_count')}")
    print(f"write_attempt_count={summary.get('write_attempt_count')}")
    print(f"output={result.get('output_path')}")
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
