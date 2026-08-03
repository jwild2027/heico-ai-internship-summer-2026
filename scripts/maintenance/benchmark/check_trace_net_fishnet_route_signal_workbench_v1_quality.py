#!/usr/bin/env python3
"""Quality checker wrapper for TRACE-Net fishnet route signal workbench v1."""
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_fishnet_route_signal_workbench_v1 import main_check

if __name__ == "__main__":
    raise SystemExit(main_check())
