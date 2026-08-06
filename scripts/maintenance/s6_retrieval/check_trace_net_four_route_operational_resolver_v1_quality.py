import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_four_route_operational_resolver_v1 import main_check

if __name__ == "__main__":
    main_check()
