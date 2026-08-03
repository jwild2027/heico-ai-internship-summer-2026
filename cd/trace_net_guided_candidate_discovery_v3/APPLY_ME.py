from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
FILES = ROOT / "files"
TARGETS = [
    (FILES / "scripts/operations/retrieval/run_trace_net_guided_candidate_discovery_v3.py", Path("scripts/operations/retrieval/run_trace_net_guided_candidate_discovery_v3.py")),
    (FILES / "tests" / "unit" / "test_trace_net_guided_candidate_discovery_v3.py", Path("tests/unit/test_trace_net_guided_candidate_discovery_v3.py")),
    (FILES / "docs" / "trace_net_guided_candidate_discovery_v3_README.md", Path("docs/trace_net_guided_candidate_discovery_v3_README.md")),
]
for src, dst in TARGETS:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"wrote {dst}")
