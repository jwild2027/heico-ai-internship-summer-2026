#!/usr/bin/env python
"""Run TRACE-Net vector search smoke v1.

This wrapper can be executed directly as:
    python scripts/run_trace_net_vector_search_smoke_v1.py ...

When Python executes a file from scripts/, sys.path points at scripts/ rather
than the repository root. Add the repo root explicitly so imports from tiff/
work in Git Bash, PowerShell, and CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_vector_search_smoke_v1 import main


if __name__ == "__main__":
    raise SystemExit(main())
