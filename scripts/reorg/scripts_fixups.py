"""Phase 5-6 fixups after moving scripts into <verb>/<stage>/:

1. parents depth-shift on each MOVED script: bump real Path(__file__)...parents[K]
   -> parents[K+D] (D = added dir depth), string-literal-aware.
2. reference update: replace every hardcoded old script path string (e.g.
   Path("scripts/benchmark/run_X.py")) with its new path, repo-wide.
3. coupled test assertions: tests that assert `"...parents[K]" in <script text>`
   must assert the moved script's NEW K; bump their string-literal parents[K] by
   the referenced script's D.
Zero deletions.
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

PAT = re.compile(r"parents\[(\d+)\]")


def norm(p):
    return p.replace("\\", "/")


def string_spans(line):
    spans, q, start = [], None, 0
    for i, c in enumerate(line):
        if q is None and c in "\"'":
            q, start = c, i
        elif q is not None and c == q and line[i - 1:i] != "\\":
            spans.append((start, i)); q = None
    return spans


def bump_real_parents(text, D):
    if D == 0 or "__file__" not in text or not PAT.search(text):
        return text, 0
    out, n = [], 0
    for line in text.split("\n"):
        spans = string_spans(line)
        cnt = [0]

        def repl(m, spans=spans, cnt=cnt):
            if any(s <= m.start() < e for s, e in spans):
                return m.group(0)
            cnt[0] += 1
            return f"parents[{int(m.group(1)) + D}]"
        out.append(PAT.sub(repl, line))
        n += cnt[0]
    return "\n".join(out), n


def bump_string_parents(text, D):
    """Bump parents[K] ONLY inside string literals (for the assertion tests)."""
    if D == 0 or not PAT.search(text):
        return text, 0
    out, n = [], 0
    for line in text.split("\n"):
        spans = string_spans(line)
        cnt = [0]

        def repl(m, spans=spans, cnt=cnt):
            if any(s <= m.start() < e for s, e in spans):
                cnt[0] += 1
                return f"parents[{int(m.group(1)) + D}]"
            return m.group(0)
        out.append(PAT.sub(repl, line))
        n += cnt[0]
    return "\n".join(out), n


moves = [ln.split("\t") for ln in Path("scripts/reorg/_scripts_moved.tsv").read_text(encoding="utf-8").splitlines() if "\t" in ln]
moves = [(norm(a), norm(b)) for a, b in moves]
D_of = {new: len(new.split("/")) - len(old.split("/")) for old, new in moves}
base2D = {Path(new).name: D_of[new] for _, new in moves}
old2new = {old: new for old, new in moves}

# 1. parents bump on moved scripts
sbump = 0
for old, new in moves:
    p = Path(new)
    txt = p.read_bytes().decode("utf-8")
    nt, n = bump_real_parents(txt, D_of[new])
    if n:
        p.write_text(nt, encoding="utf-8"); sbump += n

# 2+3. reference update + coupled assertion bump, across likely ref holders
scan = [f for f in subprocess.run(["git", "ls-files", "src", "tests", "scripts", "docs"], capture_output=True, text=True).stdout.split("\n")
        if f.strip().endswith((".py", ".md", ".sh"))]
ref_updates = 0
assert_bumps = 0
changed = []
for f in scan:
    fp = Path(f)
    try:
        txt = fp.read_bytes().decode("utf-8")
    except Exception:
        continue
    orig = txt
    # 2. replace old script paths -> new (both the path string form AND the dotted
    # module-import form, e.g. `import scripts.maintenance.tables.check_X`).
    for old, new in moves:
        if old in txt:
            txt = txt.replace(old, new)
            ref_updates += 1
        old_dot, new_dot = old[:-3].replace("/", "."), new[:-3].replace("/", ".")
        if old_dot in txt:
            txt = txt.replace(old_dot, new_dot)
            ref_updates += 1
        # module from-import: `from scripts.<oldpkg> import <mod>` -> new pkg
        old_pkg = ".".join(old.split("/")[:-1])
        new_pkg = ".".join(new.split("/")[:-1])
        mod = Path(old).stem
        if old_pkg != new_pkg:
            pat = rf"from {re.escape(old_pkg)} import {re.escape(mod)}\b"
            if re.search(pat, txt):
                txt = re.sub(pat, f"from {new_pkg} import {mod}", txt)
                ref_updates += 1
    # 3. if this file now references a moved script's NEW path AND asserts parents in
    # a string, bump that string parents by the referenced script's D.
    if f.startswith("tests/"):  # coupled assertion bumps only apply to test files
        referenced_D = set()
        for old, new in moves:
            if new in txt:
                referenced_D.add(D_of[new])
        if len(referenced_D) == 1:
            (D,) = tuple(referenced_D)
            txt, n = bump_string_parents(txt, D)
            assert_bumps += n
    if txt != orig:
        fp.write_text(txt, encoding="utf-8"); changed.append(f)

# stage everything (batched by dir to avoid arg-length limits)
for d in ("scripts", "tests", "docs"):
    subprocess.run(["git", "add", d])
print(f"script parents bumps: {sbump}")
print(f"reference-path updates: {ref_updates}  (files changed: {len(changed)})")
print(f"coupled assertion parents bumps: {assert_bumps}")
