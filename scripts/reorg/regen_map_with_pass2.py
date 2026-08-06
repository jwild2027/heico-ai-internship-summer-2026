"""Apply the Phase-1 second-pass sub-leaf overrides to REORG_PHASE1_SRC_MAP.md.

Reads the existing map table, overlays the content-derived proposed_path/why for the
211 files in the four oversized buckets (from scripts/reorg/_pass2/*.result.tsv),
recomputes one-file-leaf flags across the NEW proposed set, and rewrites the map.
Moves nothing.
"""
from __future__ import annotations
import re
from pathlib import Path
from collections import Counter

MAP = Path("REORG_PHASE1_SRC_MAP.md")
PASS2 = Path("scripts/reorg/_pass2")

# 1. Parse existing map rows: | `cur` | `prop` | why | flag |
row_re = re.compile(r"^\| `([^`]+)` \| `([^`]+)` \| (.*?) \| (.*?) \|$")
rows: list[list[str]] = []
header_lines: list[str] = []
for line in MAP.read_text(encoding="utf-8").splitlines():
    m = row_re.match(line)
    if m:
        rows.append([m.group(1), m.group(2), m.group(3), m.group(4)])
    elif not line.startswith("|"):
        header_lines.append(line)

# 2. Load overrides
overrides: dict[str, tuple[str, str]] = {}
buckets_applied: dict[str, int] = {}
for tsv in sorted(PASS2.glob("*.result.tsv")):
    n = 0
    for ln in tsv.read_text(encoding="utf-8").splitlines():
        parts = ln.rstrip("\n").split("\t")
        if len(parts) < 2 or not parts[0].strip():
            continue
        cur = parts[0].strip()
        prop = parts[1].strip().replace("\\", "/")
        why = (parts[2].strip() if len(parts) > 2 else "pass2 content-derived")
        overrides[cur] = (prop, why)
        n += 1
    buckets_applied[tsv.name] = n

# 3. Apply overrides
applied = 0
missing = []
for r in rows:
    cur = r[0]
    if cur in overrides:
        prop, why = overrides[cur]
        r[1] = prop
        r[2] = why
        r[3] = "PASS2"
        applied += 1
# report any override current_path not found in map (agent drift)
map_currents = {r[0] for r in rows}
for cur in overrides:
    if cur not in map_currents:
        missing.append(cur)

# 3b. Decision (3): approve the table->s6 retrieval bridges (clear PENDING flag).
for r in rows:
    if "PENDING decision" in r[3]:
        r[3] = "APPROVED cross-stage: table->s6/search (decision 3)"

# 4. Decision (2): iteratively bump any one-file leaf UP one level until none remain.
# (__init__.py markers don't count toward a leaf's population.) This yields exactly
# the requested homes: the 3 engram singletons land directly under s5_engram/, and
# the 2 *_quality singletons sit beside what they validate.
def _leafparent(p):
    return str(Path(p.replace("\\", "/")).parent).replace("\\", "/")

for r in rows:
    r[3] = re.sub(r";?\s*ONE-FILE-LEAF[^|]*", "", r[3]).strip()

while True:
    counts = Counter(_leafparent(r[1]) for r in rows if Path(r[0]).name != "__init__.py")
    bumped = False
    for r in rows:
        if Path(r[0]).name == "__init__.py":
            continue
        par = _leafparent(r[1])
        # never relocate the in-place exceptions (proposed == current)
        if r[1].replace("\\", "/") == r[0].replace("\\", "/"):
            continue
        if counts[par] == 1:
            p = Path(r[1].replace("\\", "/"))
            r[1] = str(p.parent.parent / p.name).replace("\\", "/")
            bumped = True
    if not bumped:
        break

# 4b. Decision (1): confirm nothing maps into s1_classify (empty stage is dropped).
s1 = [r for r in rows if "/s1_classify/" in r[1].replace("\\", "/")]

# 5. Rewrite map
out = ["# Phase 1 — src/trace_net target map (READ-ONLY proposal, nothing moved)", "",
       f"Total files: {len(rows)}. Four oversized leaves refined by content in pass 2 "
       f"(validation/scoring, ingestion/pipeline, visual/vqa, writing/output).", "",
       "| current_path | proposed_path | why | FLAG |", "|---|---|---|---|"]
for cur, prop, why, flag in sorted(rows, key=lambda r: r[1]):
    out.append(f"| `{cur}` | `{prop}` | {why} | {flag} |")
MAP.write_text("\n".join(out) + "\n", encoding="utf-8")

print("override files:", buckets_applied)
print("overrides applied:", applied, " (loaded:", len(overrides), ")")
if missing:
    print("WARNING: override current_paths NOT in map:", len(missing))
    for m in missing[:20]:
        print("   ", m)

# ---- LOCK VERIFICATION ----
real_leaf_counts = Counter(_leafparent(r[1]) for r in rows if Path(r[0]).name != "__init__.py")
one_file = [leaf for leaf, n in real_leaf_counts.items() if n == 1]
pending = [r[0] for r in rows if "PENDING" in r[3]]
distinct_leaves = len({_leafparent(r[1]) for r in rows if Path(r[0]).name != "__init__.py"})
print("\n==== LOCK VERIFICATION ====")
print("total files          :", len(rows))
print("distinct target leaves:", distinct_leaves)
print("one-file leaves       :", len(one_file), one_file if one_file else "(zero)")
print("PENDING flags         :", len(pending), pending if pending else "(zero)")
print("files under s1_classify:", len(s1), "(folder dropped)" if not s1 else s1)

print("\n=== NEW sub-leaves under the four refined subtrees (counts) ===")
for prefix in ("src/trace_net/validation/", "src/trace_net/ingestion/",
               "src/trace_net/visual/", "src/trace_net/writing/"):
    print(f"-- {prefix}")
    sub = Counter()
    for _, p, _, _ in rows:
        pp = p.replace("\\", "/")
        if pp.startswith(prefix):
            sub[str(Path(pp).parent).replace("\\", "/")] += 1
    for leaf, c in sorted(sub.items()):
        print(f"   {c:4d}  {leaf}")
