"""Phase 7-8 — sort the archive zone into themed sub-folders under archive/, keeping
every bundle folder intact. cd/, patches/, tools/patch_archive/ stay THREE separate
trees; legacy/ is grouped by why-it's-dead. git mv only (dirs/files as units).

--map : print the plan   --go : execute
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path


def dirs_under(top):
    out = subprocess.run(["git", "ls-files", top], capture_output=True, text=True).stdout.split("\n")
    return sorted({f.split("/")[1] for f in out if f.startswith(top + "/") and "/" in f[len(top) + 1:]})


def files_under(top):
    out = subprocess.run(["git", "ls-files", top], capture_output=True, text=True).stdout.split("\n")
    return sorted(f for f in out if f.startswith(top + "/") and "/" not in f[len(top) + 1:])


def cd_theme(b):
    order = [("guided_candidate_discovery", "guided_discovery"), ("stack_launcher", "openwebui_stack"),
             ("openwebui", "openwebui_stack"), ("demo_stack", "openwebui_stack"),
             ("router_proxy", "router"), ("guided_discovery_router_proxy", "router"),
             ("confirmed_image", "image_visual"), ("gemma_visual", "image_visual"),
             ("image_route", "image_visual"), ("visual_question_context", "image_visual"),
             ("tiff_content", "tiff_content"), ("engram", "engram"), ("table", "table"),
             ("router", "router"), ("benchmark", "benchmark"), ("gemma_mode", "benchmark")]
    for kw, th in order:
        if kw in b:
            return th
    return "misc"


def patches_theme(b):
    for kw, th in [("engram", "engram"), ("trace_server", "trace_server"), ("answer_overlay", "answer_overlay")]:
        if kw in b:
            return th
    return "misc"


def patch_archive_theme(fn):
    if "page_image" in fn or "page_visual" in fn:
        return "page_image"
    if "streamlit" in fn:
        return "streamlit"
    if "engram" in fn:
        return "engram"
    if re.search(r"_h\d", fn):
        return "router_h"
    return "misc"


LEGACY_WHY = {"duplicate_src": "superseded", "src_prototypes": "prototypes", "model_wrappers": "model_wrappers",
              "vendor_snapshots": "vendor", "tiff_package_markers": "markers", "tiff_backups": "backups",
              "scripts": "backups"}


def build_ops():
    ops = []  # (src, dst)
    for b in dirs_under("cd"):
        ops.append((f"cd/{b}", f"archive/cd/{cd_theme(b)}/{b}"))
    for b in dirs_under("patches"):
        ops.append((f"patches/{b}", f"archive/patches/{patches_theme(b)}/{b}"))
    for f in files_under("tools/patch_archive"):
        ops.append((f, f"archive/patch_archive/{patch_archive_theme(Path(f).name)}/{Path(f).name}"))
    for d in dirs_under("legacy"):
        ops.append((f"legacy/{d}", f"archive/legacy/{LEGACY_WHY.get(d, 'misc')}/{d}"))
    return ops


def main(go):
    ops = build_ops()
    from collections import Counter
    print(f"archive ops: {len(ops)}")
    for grp in ("archive/cd", "archive/patches", "archive/patch_archive", "archive/legacy"):
        c = Counter(dst.split("/")[2] for _, dst in ops if dst.startswith(grp + "/"))
        print(f"-- {grp}: " + ", ".join(f"{k}({v})" for k, v in sorted(c.items())))
    if not go:
        for s, d in ops:
            print(f"  {s}  ->  {d}")
        return 0
    moved = 0
    for s, d in ops:
        Path(d).parent.mkdir(parents=True, exist_ok=True)
        rc = subprocess.run(["git", "mv", s, d], capture_output=True, text=True)
        if rc.returncode != 0:
            print("ABORT git mv failed:", s, "->", d, rc.stderr); return 3
        moved += 1
    print(f"moved={moved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(go="--go" in sys.argv))
