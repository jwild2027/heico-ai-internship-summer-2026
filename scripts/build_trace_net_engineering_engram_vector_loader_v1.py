#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_engineering_engram_vector_loader_v1 import build_vector_loader_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net Engineering Engram vector loader manifest v1")
    p.add_argument("--memory-layers", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--collection-name", default="trace_net_engineering_engram_memory_v1")
    p.add_argument("--vector-dim", type=int, default=64)
    p.add_argument("--min-records", type=int, default=1)
    p.add_argument("--require-all-layers", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = build_vector_loader_manifest(
        memory_layers=args.memory_layers,
        output_dir=args.output_dir,
        vector_dim=args.vector_dim,
        collection_name=args.collection_name,
        min_records=args.min_records,
        require_all_layers=args.require_all_layers,
        max_unsafe=args.max_unsafe,
    )
    summary = manifest.get("summary", {})
    print(f"status={manifest.get('status')}")
    print(f"quality_status={manifest.get('quality_status')}")
    print(f"qdrant_ready_record_count={summary.get('qdrant_ready_record_count')}")
    print(f"vector_dim={summary.get('vector_dim')}")
    print(f"unsafe_finding_count={summary.get('unsafe_finding_count')}")
    print(f"answer_permission_count={summary.get('answer_permission_count')}")
    print(f"write_attempt_count={summary.get('write_attempt_count')}")
    print(f"output={Path(args.output_dir) / 'trace_net_engineering_engram_vector_loader_v1.json'}")
    return 0 if manifest.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
