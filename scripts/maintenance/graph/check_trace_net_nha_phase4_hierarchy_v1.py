#!/usr/bin/env python3
"""Independently validate TRACE-Net NHA phase N4 hierarchy artifacts."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trace_net.graph.trace_net_nha_phase4_hierarchy_v1 import _load_records, validate_phase4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--minimum-supported", type=int, default=1)
    parser.add_argument("--minimum-attaching-supported", type=int, default=1)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.output_dir).resolve()
    hierarchy_rows = _load_records(root / "trace_net_nha_hierarchy_rows_v1.json")
    relationships = _load_records(root / "trace_net_nha_hierarchy_relationships_v1.json")
    groups = _load_records(root / "trace_net_nha_attaching_groups_v1.json")
    result = validate_phase4(
        hierarchy_rows,
        relationships,
        groups,
        minimum_supported=args.minimum_supported,
        minimum_attaching_supported=args.minimum_attaching_supported,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.strict and result["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE4_CHECK=FAIL")
    print("TRACE_NET_NHA_PHASE4_CHECK=PASS" if result["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE4_CHECK=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
