import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tiff.trace_net_engineering_webui_answer_server_v1 import main_build
if __name__ == "__main__":
    raise SystemExit(main_build())
