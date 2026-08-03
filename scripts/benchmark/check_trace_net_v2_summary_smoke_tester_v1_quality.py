#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tiff.trace_net_v2_summary_smoke_tester_v1 import check_main

if __name__ == "__main__":
    raise SystemExit(check_main())
