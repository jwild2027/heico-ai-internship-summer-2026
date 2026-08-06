"""Restore pristine HEAD content at each moved script's NEW path, so the move
commits as a pure rename (100% similarity -> git detects rename -> 0 deletions).
The content fixups are re-applied afterward as a separate in-place commit.
"""
import subprocess
from pathlib import Path

moves = [ln.split("\t") for ln in Path("scripts/reorg/_scripts_moved.tsv").read_text(encoding="utf-8").splitlines() if "\t" in ln]
n = 0
for old, new in moves:
    old = old.replace("\\", "/"); new = new.replace("\\", "/")
    r = subprocess.run(["git", "show", f"HEAD:{old}"], capture_output=True)
    if r.returncode != 0:
        print("WARN no HEAD content:", old); continue
    Path(new).write_bytes(r.stdout)   # exact original bytes -> identical -> rename
    n += 1
print("restored pristine at new paths:", n)
