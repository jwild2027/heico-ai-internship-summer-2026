#!/usr/bin/env python3
"""CLI wrapper for TRACE-Net LLaVA visual summary batch v1."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_llava_visual_summary_batch_v1 import main

if __name__ == "__main__":
    raise SystemExit(main())
