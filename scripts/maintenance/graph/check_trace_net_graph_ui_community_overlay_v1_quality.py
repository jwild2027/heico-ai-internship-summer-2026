#!/usr/bin/env python
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_graph_ui_community_overlay_v1 import quality_main

if __name__ == "__main__":
    raise SystemExit(quality_main())
