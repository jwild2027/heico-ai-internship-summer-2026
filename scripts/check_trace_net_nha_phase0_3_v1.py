#!/usr/bin/env python3
"""Check an existing TRACE-Net NHA phase N0-N3 output directory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

# Keep the checker runnable as a direct script from any working directory.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.trace_net_nha_phase0_3_v1 import validate_artifacts


def _records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("records") if isinstance(payload, Mapping) else None
    return [dict(row) for row in rows or [] if isinstance(row, Mapping)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-page-count", type=int, default=509)
    parser.add_argument("--min-source-supported", type=int, default=1)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = Path(args.output_dir)
    inventory = _records(root / "trace_net_nha_page_inventory_v1.json")
    anchors = _records(root / "trace_net_nha_assembly_anchors_v1.json")
    rows = _records(root / "trace_net_nha_ipl_rows_v1.json")
    relationships = _records(root / "trace_net_nha_relationships_v1.json")
    result = validate_artifacts(
        inventory,
        anchors,
        rows,
        relationships,
        expected_page_count=args.expected_page_count,
        min_source_supported=args.min_source_supported,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.strict and result["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE0_3_CHECK=FAIL")
    print(f"TRACE_NET_NHA_PHASE0_3_CHECK={result['quality_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
