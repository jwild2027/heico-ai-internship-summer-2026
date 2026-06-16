#!/usr/bin/env python
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_leiden_category_summary_hydrator_v1 import main

if __name__ == "__main__":
    raise SystemExit(main())
