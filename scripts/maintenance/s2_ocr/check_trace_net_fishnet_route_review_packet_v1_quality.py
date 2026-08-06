#!/usr/bin/env python
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_fishnet_route_review_packet_v1 import main_quality

if __name__ == "__main__":
    raise SystemExit(main_quality())
