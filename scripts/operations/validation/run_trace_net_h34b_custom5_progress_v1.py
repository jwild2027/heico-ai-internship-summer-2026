from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tiff.trace_net_h34_custom_question_progress_runner_v1 import main
raise SystemExit(main())
