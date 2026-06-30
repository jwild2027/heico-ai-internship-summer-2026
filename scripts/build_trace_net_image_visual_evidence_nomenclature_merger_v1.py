from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tiff.trace_net_image_visual_evidence_nomenclature_merger_v1 import main

if __name__ == "__main__":
    raise SystemExit(main(["build", *sys.argv[1:]]))
