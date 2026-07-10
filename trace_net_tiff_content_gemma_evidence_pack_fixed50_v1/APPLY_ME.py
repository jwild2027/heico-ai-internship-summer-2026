from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "files"
DEST = ROOT.parent
for path in SRC.rglob("*"):
    if path.is_file():
        rel = path.relative_to(SRC)
        out = DEST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
        print(f"copied {rel}")
print("APPLY_DONE trace_net_tiff_content_gemma_evidence_pack_fixed50_v1")
