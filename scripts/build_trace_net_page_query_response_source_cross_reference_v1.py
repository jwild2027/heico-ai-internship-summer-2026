from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_page_query_response_source_cross_reference_v1 import main_build

if __name__ == "__main__":
    raise SystemExit(main_build())
