import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_table_structure_bbox_localizer_v1_quality import main

if __name__ == "__main__":
    raise SystemExit(main())
