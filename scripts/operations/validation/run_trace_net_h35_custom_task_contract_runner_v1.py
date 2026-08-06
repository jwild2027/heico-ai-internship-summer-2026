from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_h35_custom_task_contract_runner_v1 import main

if __name__ == "__main__":
    raise SystemExit(main())
