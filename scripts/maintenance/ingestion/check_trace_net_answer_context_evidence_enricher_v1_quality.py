from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_answer_context_evidence_enricher_v1 import main_check

if __name__ == "__main__":
    main_check()
