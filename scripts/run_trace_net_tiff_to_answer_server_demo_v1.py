#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.trace_net_tiff_to_answer_server_demo_v1 import main

if __name__ == "__main__":
    raise SystemExit(main())
