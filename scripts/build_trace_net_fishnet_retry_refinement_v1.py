#!/usr/bin/env python3
"""Build TRACE-Net fishnet retry refinement v1."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_fishnet_retry_refinement_v1 import main

if __name__ == "__main__":
    raise SystemExit(main())
