from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
PATCH = Path(__file__).resolve().parent / "files"

for src in PATCH.rglob("*"):
    if src.is_file():
        rel = src.relative_to(PATCH)
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"wrote {rel}")

print("PATCH_APPLIED trace_net_fixed50_trace_server_gemma_multiquery_progress_v1")
