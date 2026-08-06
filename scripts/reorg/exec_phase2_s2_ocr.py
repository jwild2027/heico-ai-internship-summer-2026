"""Phase 2 executor for the s2_ocr stage ONLY.

For each locked-map row whose proposed_path is under pipeline/s2_ocr/ (and != current):
  1. git mv current -> proposed  (creating destination dirs first)
  2. write a one-line re-export shim at the OLD path (src/vector/chroma_client.py pattern)
Then create __init__.py in every new package dir and git add shims + inits.

NEVER deletes. `git mv` preserves history; shims and __init__.py are adds.
Run with --dry-run to preview; run with --go to execute.
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(".")
MAP = Path("REORG_PHASE1_SRC_MAP.md")
SHIM = (
    '"""Compatibility shim (repo reorg — reorg: s2_ocr). Moved to ``{mod}``.\n\n'
    "Importing from this old path keeps working: it re-exports the relocated module in full.\n"
    'Update imports to the new path when convenient.\n"""\n'
    "import importlib as _importlib\n"
    "import sys as _sys\n"
    '_sys.modules[__name__] = _importlib.import_module("{mod}")\n'
)


def norm(p: str) -> str:
    return p.replace("\\", "/")


def module_of(path: str) -> str:
    return norm(path)[:-3].replace("/", ".")


def sh(*args) -> tuple[int, str]:
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main(go: bool) -> int:
    rows = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \|", MAP.read_text(encoding="utf-8"), re.M)
    scope = [(norm(c), norm(p)) for c, p in rows
             if "/pipeline/s2_ocr/" in norm(p) and norm(c) != norm(p)]
    missing = [c for c, _ in scope if not Path(c).exists()]
    if missing:
        print("ABORT — sources missing on disk:", missing)
        return 2

    # package dirs that must exist (every ancestor under src/trace_net/pipeline)
    pkg_dirs: set[str] = set()
    for _, p in scope:
        d = Path(p).parent
        while norm(str(d)).startswith("src/trace_net/pipeline"):
            pkg_dirs.add(norm(str(d)))
            d = d.parent
    pkg_dirs.add("src/trace_net/pipeline")

    print(f"stage=s2_ocr  files_to_move={len(scope)}  new_package_dirs={len(pkg_dirs)}  mode={'GO' if go else 'DRY-RUN'}")
    if not go:
        for c, p in scope:
            print(f"  MV  {c}  ->  {p}")
            print(f"  SHIM {c}  ->  import {module_of(p)}")
        return 0

    moved = shims = inits = 0
    # 1+2: move then shim
    for c, p in scope:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        rc, out = sh("git", "mv", c, p)
        if rc != 0:
            print(f"ABORT git mv failed: {c} -> {p}\n{out}")
            return 3
        moved += 1
        Path(c).write_text(SHIM.format(mod=module_of(p)), encoding="utf-8")
        shims += 1
    # 3: __init__.py for new package dirs
    for d in sorted(pkg_dirs):
        ip = Path(d) / "__init__.py"
        if not ip.exists():
            ip.write_text("", encoding="utf-8")
            inits += 1
    # git add shims + inits (moves already staged by git mv)
    sh("git", "add", "--", *[c for c, _ in scope])
    sh("git", "add", "--", *[str(Path(d) / "__init__.py") for d in pkg_dirs])
    print(f"DONE  moved={moved}  shims_written={shims}  init_files_added={inits}")
    # deletion guard
    rc, out = sh("git", "diff", "--cached", "--diff-filter=D", "--name-only")
    print("staged deletions (must be empty):", out or "(none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(go="--go" in sys.argv))
