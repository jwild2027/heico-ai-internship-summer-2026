"""Phase 3-4 — mirror tests/unit/ onto the final committed src/trace_net/ layout.

Each unit test is mapped to the leaf of the src module it exercises: resolve the
modules it references (tiff.X / src.trace_net... imports, hardcoded Path("src/...")
and spec_from_file_location), look up each module's FINAL location in the locked
map, and place the test under tests/unit/<mirror-of-that-leaf>/. Tests that resolve
to no src module stay in tests/unit/ root. tests/{integration,regression,fixtures,
data} are untouched. No shims for tests. git mv only; zero deletions.

--map : write REORG_TESTS_MAP.md + print summary (moves nothing)
--go  : execute git mv per the map, then git add
"""
from __future__ import annotations
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

MAP = Path("REORG_PHASE1_SRC_MAP.md")
ROWS = [(c.replace("\\", "/"), p.replace("\\", "/"))
        for c, p in re.findall(r"^\| `([^`]+)` \| `([^`]+)` \|", MAP.read_text(encoding="utf-8"), re.M)]
# module basename -> FINAL path (basenames are unique repo-wide)
BASE2FINAL = {Path(p).name: p for _, p in ROWS}
BASE2FINAL.update({Path(c).name: p for c, p in ROWS})  # old basename also maps (same name)

REF_RES = [
    re.compile(r"from\s+tiff\.([A-Za-z0-9_]+)\s+import"),
    re.compile(r"import\s+tiff\.([A-Za-z0-9_]+)"),
    re.compile(r"from\s+src\.trace_net\.[A-Za-z0-9_.]*?([A-Za-z0-9_]+)\s+import"),
    re.compile(r'Path\("src/trace_net/[^"]*?([A-Za-z0-9_]+)\.py"\)'),
    re.compile(r'spec_from_file_location\([^,]+,\s*[^)]*?([A-Za-z0-9_]+)\.py'),
]


def leaf_rel(final_path: str) -> str | None:
    """final src path -> mirror dir relative to src/trace_net/ (the leaf dir)."""
    pref = "src/trace_net/"
    if not final_path.startswith(pref):
        return None
    return str(Path(final_path[len(pref):]).parent).replace("\\", "/")


def resolve_test(txt: str):
    """Return (target_leaf_rel, driving_module) or (None, None)."""
    leaves = Counter()
    drivers = {}
    for rx in REF_RES:
        for m in rx.findall(txt):
            fp = BASE2FINAL.get(m + ".py")
            if fp:
                lr = leaf_rel(fp)
                if lr:
                    leaves[lr] += 1
                    drivers.setdefault(lr, m)
    if not leaves:
        return None, None
    top = leaves.most_common(1)[0][0]
    return top, drivers[top]


def main(go: bool):
    tests = sorted(str(Path(p)) .replace("\\", "/") for p in
                   subprocess.run(["git", "ls-files", "tests/unit"], capture_output=True, text=True).stdout.split("\n")
                   if p.strip().endswith(".py"))
    rows = []
    for t in tests:
        base = Path(t).name
        if base == "__init__.py" or base == "conftest.py":
            continue
        txt = Path(t).read_text(encoding="utf-8", errors="replace")
        lr, drv = resolve_test(txt)
        if lr is None:
            rows.append((t, t, "", "unresolved-stays-in-root"))
            continue
        target = f"tests/unit/{lr}/{base}"
        rows.append((t, target.replace("\\", "/"), drv, lr))

    moves = [(c, p) for c, p, *_ in rows if c != p]
    lines = ["# Phase 3-4 tests mirror map", "",
             f"unit test files: {len(rows)}  |  to move: {len(moves)}  |  staying in root: {len(rows)-len(moves)}",
             "", "| current | proposed | driving_module | leaf |", "|---|---|---|---|"]
    for c, p, drv, lr in sorted(rows, key=lambda r: r[1]):
        lines.append(f"| `{c}` | `{p}` | {drv} | {lr} |")
    Path("REORG_TESTS_MAP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    leafc = Counter(str(Path(p).parent).replace("\\", "/") for c, p in moves)
    print(f"unit tests: {len(rows)}  to_move: {len(moves)}  staying_root: {len(rows)-len(moves)}")
    print("=== target leaves (counts) ===")
    for leaf, n in sorted(leafc.items()):
        print(f"{n:4d}  {leaf}")

    if not go:
        return 0
    moved = 0
    for c, p in moves:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        rc = subprocess.run(["git", "mv", c, p], capture_output=True, text=True)
        if rc.returncode != 0:
            print("ABORT git mv failed:", c, "->", p, rc.stderr)
            return 3
        moved += 1
    # No __init__.py: pytest collects recursively via rootdir; test basenames are
    # unique, so prepend-import mode handles subdirs without packages.

    # Fixup: some tests import helpers from other tests via `from tests.unit.NAME
    # import ...`. When NAME moved into a subdir, rewrite to its new dotted path
    # (namespace packages resolve the deeper path). Zero deletions.
    name2new = {}
    for c, p in moves:
        rel = str(Path(p).parent).replace("\\", "/")[len("tests/unit/"):].replace("/", ".")
        name2new[Path(c).stem] = f"tests.unit.{rel}.{Path(p).stem}"
    fixed = 0
    for f in subprocess.run(["git", "ls-files", "tests/unit"], capture_output=True, text=True).stdout.split("\n"):
        if not f.strip().endswith(".py"):
            continue
        fp = Path(f)
        txt = fp.read_text(encoding="utf-8", errors="replace")
        orig = txt
        for nm, newdot in name2new.items():
            txt = re.sub(rf"from tests\.unit\.{re.escape(nm)} import", f"from {newdot} import", txt)
        if txt != orig:
            fp.write_text(txt, encoding="utf-8")
            subprocess.run(["git", "add", "--", f], capture_output=True, text=True)
            fixed += 1
    print(f"moved={moved}  inter_test_import_fixups={fixed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(go="--go" in sys.argv))
