from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
FILES = ROOT / "files"
TARGET = Path.cwd()

for src in FILES.rglob("*"):
    if src.is_file():
        rel = src.relative_to(FILES)
        dst = TARGET / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"wrote {dst}")
print("Applied trace_net_guided_candidate_discovery_v1")
