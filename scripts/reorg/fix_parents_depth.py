"""Fourth auto-fix (string-literal-aware) + inter-test import fixup, done from the
PRISTINE UTF-8 originals.

For every moved test: restore content from HEAD:tests/unit/<base> decoded as UTF-8
(NOT the Windows locale codec — that was corrupting em-dashes etc.), then apply:
  1. parents depth-shift: bump REAL Path(__file__)...parents[K] -> parents[K+D];
     leave parents[N] inside string literals untouched (they assert other files).
  2. inter-test import fixup: from tests.unit.NAME import ... -> new dotted path
     when NAME moved into a subdir.
Zero deletions.
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

PAT = re.compile(r"parents\[(\d+)\]")


def norm(p: str) -> str:
    return p.replace("\\", "/")


def show_utf8(path: str) -> str | None:
    r = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8")


def string_spans(line: str):
    spans, q, start = [], None, 0
    for i, c in enumerate(line):
        if q is None and c in "\"'":
            q, start = c, i
        elif q is not None and c == q and line[i - 1:i] != "\\":
            spans.append((start, i)); q = None
    return spans


all_tests = [norm(f) for f in subprocess.run(["git", "ls-files", "tests/unit"], capture_output=True, text=True).stdout.split("\n")
             if f.strip().endswith(".py")]
moved = [f for f in all_tests if norm(str(Path(f).parent)) != "tests/unit"]
# new dotted path for every test now in a subdir (for inter-test import rewrites)
stem2dot = {}
for f in moved:
    rel = norm(str(Path(f).parent))[len("tests/unit/"):].replace("/", ".")
    stem2dot[Path(f).stem] = f"tests.unit.{rel}.{Path(f).stem}"

parents_fixed = inter_fixed = 0
for f in moved:
    base = Path(f).name
    text = show_utf8(f"tests/unit/{base}")
    if text is None:
        continue
    D = len(norm(str(Path(f).parent))[len("tests/unit/"):].split("/"))
    # 1. parents depth-shift (skip string literals)
    if "__file__" in text and PAT.search(text):
        out = []
        for line in text.split("\n"):
            spans = string_spans(line)
            cnt = [0]

            def repl(m, spans=spans, cnt=cnt):
                if any(s <= m.start() < e for s, e in spans):
                    return m.group(0)
                cnt[0] += 1
                return f"parents[{int(m.group(1)) + D}]"
            nl = PAT.sub(repl, line)
            if cnt[0]:
                parents_fixed += cnt[0]
            out.append(nl)
        text = "\n".join(out)
    # 2. inter-test import fixup
    before = text
    for stem, dot in stem2dot.items():
        text = re.sub(rf"from tests\.unit\.{re.escape(stem)} import", f"from {dot} import", text)
    if text != before:
        inter_fixed += 1
    Path(f).write_text(text, encoding="utf-8")

print(f"moved tests reconstructed (UTF-8): {len(moved)}")
print(f"real parents[] bumps: {parents_fixed}   inter-test import fixups: {inter_fixed}")
