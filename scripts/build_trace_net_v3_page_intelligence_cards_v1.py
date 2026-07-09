#!/usr/bin/env python3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tiff.trace_net_v3_page_intelligence_cards_v1 import build_cli_main

if __name__ == "__main__":
    raise SystemExit(build_cli_main())
