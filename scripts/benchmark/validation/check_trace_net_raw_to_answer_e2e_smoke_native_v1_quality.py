from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_raw_to_answer_e2e_smoke_native_v1 import main_check

if __name__ == "__main__":
    main_check()
