from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
FILES = ROOT / "files"
for src in FILES.rglob("*"):
    if src.is_file():
        rel = src.relative_to(FILES)
        dst = Path.cwd() / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"wrote {dst}")
print("PATCH_APPLIED trace_net_fixed50_trace_server_gemma_multiquery_df_fallback_v1")
