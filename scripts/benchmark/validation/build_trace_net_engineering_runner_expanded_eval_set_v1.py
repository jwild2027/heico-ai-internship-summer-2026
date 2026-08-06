from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_engineering_runner_expanded_eval_set_v1 import main

if __name__ == "__main__":
    raise SystemExit(main())
