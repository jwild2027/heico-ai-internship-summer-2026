import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tiff.trace_net_engineering_engram_answer_smoke_overlay_integration_gate_v1 import check_main
if __name__ == "__main__":
    raise SystemExit(check_main())
