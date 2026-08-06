#!/usr/bin/env python3
from __future__ import annotations
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_engineering_engram_prompt_retrieval_smoke_v1 import build_prompt_retrieval_smoke_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--prompt-injector", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-prompt-chars", type=int, default=2200)
    p.add_argument("--min-queries", type=int, default=6)
    p.add_argument("--min-injected-atoms", type=int, default=6)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-guidance-only", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = build_prompt_retrieval_smoke_manifest(
        prompt_injector_path=args.prompt_injector,
        output_dir=args.output_dir,
        max_prompt_chars=args.max_prompt_chars,
        min_queries=args.min_queries,
        min_injected_atoms=args.min_injected_atoms,
        require_quality_pass=args.require_quality_pass,
        require_guidance_only=args.require_guidance_only,
        require_no_answer_permission=args.require_no_answer_permission,
        max_unsafe=args.max_unsafe,
        max_write_attempts=args.max_write_attempts,
    )
    s = manifest.get("summary", {})
    print("status=" + str(manifest.get("status")))
    print("quality_status=" + str(manifest.get("quality_status")))
    print("query_count=" + str(s.get("query_count")))
    print("prompt_integration_record_count=" + str(s.get("prompt_integration_record_count")))
    print("selected_atom_count=" + str(s.get("selected_atom_count")))
    print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    print("output=" + str(Path(args.output_dir) / "trace_net_engineering_engram_prompt_retrieval_smoke_v1.json"))
    return 0 if manifest.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
