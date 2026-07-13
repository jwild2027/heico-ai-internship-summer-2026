#!/usr/bin/env python3
from pathlib import Path
import shutil

patch_root = Path(__file__).resolve().parent
repo_root = Path.cwd().resolve()

if not (repo_root / "scripts").is_dir() or not (repo_root / ".git").exists():
    raise SystemExit(
        "Run APPLY_ME.py from the repository root: "
        "/c/Users/juswil/Documents/GitHub/heico-ai-internship-summer-2026"
    )

for rel in (
    Path("scripts/launch_trace_net_openwebui_full_stack_v2.py"),
    Path("tests/unit/test_trace_net_openwebui_full_stack_v2_launcher.py"),
):
    src = patch_root / rel
    dst = repo_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"applied {rel}")

print("status=TRACE_NET_V2_OPTIONAL_QDRANT_COWORKER_PATCH_APPLIED")
