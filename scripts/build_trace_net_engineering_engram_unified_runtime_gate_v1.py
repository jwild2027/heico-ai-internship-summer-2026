#!/usr/bin/env python
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tiff.trace_net_engineering_engram_unified_runtime_gate_v1 import main

if __name__ == '__main__':
    raise SystemExit(main())
