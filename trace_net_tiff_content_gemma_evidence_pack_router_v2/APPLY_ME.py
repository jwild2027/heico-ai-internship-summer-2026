from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
repo = root.parent
files = root / "files"
for src in files.rglob("*"):
    if src.is_file():
        rel = src.relative_to(files)
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"wrote {rel}")
print("APPLY_DONE trace_net_tiff_content_gemma_evidence_pack_router_v2")
