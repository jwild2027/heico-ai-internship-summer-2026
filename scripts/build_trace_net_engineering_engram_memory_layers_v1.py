#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from tiff.trace_net_engineering_engram_memory_layers_v1 import build_memory_layer_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram Memory Layers v1")
    parser.add_argument("--engram-core", required=True)
    parser.add_argument("--query-planner", action="append", default=[], help="Optional engineering query planner manifest; may be repeated.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-atoms", type=int, default=6)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--no-seed-atoms", action="store_true")
    parser.add_argument("--no-require-all-layers", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = build_memory_layer_manifest(
        engram_core_path=args.engram_core,
        output_dir=args.output_dir,
        include_seed_atoms=not args.no_seed_atoms,
        min_atoms=args.min_atoms,
        require_all_layers=not args.no_require_all_layers,
        query_planner_paths=args.query_planner,
        max_unsafe=args.max_unsafe,
    )
    output = Path(args.output_dir) / "trace_net_engineering_engram_memory_layers_v1.json"
    print(f"status={manifest.get('status')}")
    print(f"quality_status={manifest.get('quality_status')}")
    summary = manifest.get("summary", {})
    print(f"memory_layer_count={summary.get('memory_layer_count')}")
    print(f"memory_atom_count={summary.get('memory_atom_count')}")
    print(f"unsafe_finding_count={summary.get('unsafe_finding_count')}")
    print(f"answer_permission_count={summary.get('answer_permission_count')}")
    print(f"write_attempt_count={summary.get('write_attempt_count')}")
    print(f"output={output}")
    return 0 if manifest.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
