#!/usr/bin/env python3
"""CLI wrapper for TRACE-Net visual callout table linker v1 quality check."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_visual_callout_table_linker_v1_check import main

if __name__ == "__main__":
    raise SystemExit(main())
