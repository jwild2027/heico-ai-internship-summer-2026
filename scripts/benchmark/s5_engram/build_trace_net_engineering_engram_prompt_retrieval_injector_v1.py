#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_engineering_engram_prompt_retrieval_injector_v1 import build_prompt_retrieval_injector_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Prompt Retrieval Injector v1 artifact")
    p.add_argument("--vector-retriever", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-atoms-per-query", type=int, default=4)
    p.add_argument("--max-prompt-chars", type=int, default=1800)
    p.add_argument("--min-queries", type=int, default=1)
    p.add_argument("--min-injected-atoms", type=int, default=1)
    p.add_argument("--require-guidance-only", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = build_prompt_retrieval_injector_manifest(
        vector_retriever_path=args.vector_retriever,
        output_dir=args.output_dir,
        max_atoms_per_query=args.max_atoms_per_query,
        max_prompt_chars=args.max_prompt_chars,
        min_queries=args.min_queries,
        min_injected_atoms=args.min_injected_atoms,
        require_guidance_only=args.require_guidance_only,
        require_no_answer_permission=args.require_no_answer_permission,
        max_unsafe=args.max_unsafe,
        max_write_attempts=args.max_write_attempts,
    )
    summary = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"query_count={summary.get('query_count')}")
    print(f"prompt_bundle_count={summary.get('prompt_bundle_count')}")
    print(f"selected_atom_count={summary.get('selected_atom_count')}")
    print(f"max_observed_prompt_chars={summary.get('max_observed_prompt_chars')}")
    print(f"unsafe_finding_count={summary.get('unsafe_finding_count')}")
    print(f"answer_permission_count={summary.get('answer_permission_count')}")
    print(f"write_attempt_count={summary.get('write_attempt_count')}")
    print(f"output={result.get('output_path')}")
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
