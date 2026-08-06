import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_engineering_real_answer_smoke_review_v1 import check_main

if __name__ == "__main__":
    raise SystemExit(check_main())
