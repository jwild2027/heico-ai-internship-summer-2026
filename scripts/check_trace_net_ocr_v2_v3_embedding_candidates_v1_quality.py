#!/usr/bin/env python3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tiff.trace_net_ocr_v2_v3_embedding_candidates_v1 import check_cli_main

if __name__ == "__main__":
    raise SystemExit(check_cli_main())
