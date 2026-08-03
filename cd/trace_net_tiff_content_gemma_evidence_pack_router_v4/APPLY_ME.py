from pathlib import Path
import shutil

root = Path.cwd()
base = Path(__file__).resolve().parent / "files"
for src in base.rglob("*"):
    if src.is_dir():
        continue
    rel = src.relative_to(base)
    dst = root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"wrote {dst}")
print("applied trace_net_tiff_content_gemma_evidence_pack_router_v4")
