#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_engineering_engram_vector_retriever_v1 import check_vector_retriever_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Vector Retriever v1 artifact")
    p.add_argument("--vector-retriever", required=True)
    p.add_argument("--min-queries", type=int, default=1)
    p.add_argument("--min-results-per-query", type=int, default=1)
    p.add_argument("--require-all-layers", action="store_true")
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = check_vector_retriever_manifest(
        vector_retriever_path=args.vector_retriever,
        min_queries=args.min_queries,
        min_results_per_query=args.min_results_per_query,
        require_all_layers=args.require_all_layers,
        require_quality_pass=args.require_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        max_unsafe=args.max_unsafe,
        max_write_attempts=args.max_write_attempts,
    )
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"query_count={result.get('query_count')}")
    print(f"retrieval_record_count={result.get('retrieval_record_count')}")
    print(f"total_retrieved_item_count={result.get('total_retrieved_item_count')}")
    print(f"indexed_memory_layer_counts={result.get('indexed_memory_layer_counts')}")
    print(f"retrieved_memory_layer_counts={result.get('retrieved_memory_layer_counts')}")
    print(f"unsafe_finding_count={result.get('unsafe_finding_count')}")
    print(f"answer_permission_count={result.get('answer_permission_count')}")
    print(f"write_attempt_count={result.get('write_attempt_count')}")
    if result.get("failures"):
        print("failures=" + ";".join(result.get("failures") or []))
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
