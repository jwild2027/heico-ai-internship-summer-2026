"""Phase 5-6 — sort scripts into pipeline-stage sub-folders inside their verb folder.

For scripts/{maintenance,operations,benchmark}/**, resolve the src module each
script builds/checks (imports + filename) to its FINAL leaf, derive the coarse
stage bucket (s2_ocr, s3_graph_store, ..., ingestion/serving/validation/visual/
writing/core), and target scripts/<verb>/<bucket>/<script>. scripts/migration/
stays flat. Scripts that resolve to nothing stay where they are. git mv only.

--map : write REORG_SCRIPTS_MAP.md + summary   --go : execute
"""
from __future__ import annotations
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROWS = [(c.replace("\\", "/"), p.replace("\\", "/"))
        for c, p in re.findall(r"^\| `([^`]+)` \| `([^`]+)` \|",
                               Path("REORG_PHASE1_SRC_MAP.md").read_text(encoding="utf-8"), re.M)]
BASE2FINAL = {Path(p).name: p for _, p in ROWS}
BASE2FINAL.update({Path(c).name: p for c, p in ROWS})

REFS = [
    re.compile(r"from\s+tiff\.([A-Za-z0-9_]+)\s+import"),
    re.compile(r"import\s+tiff\.([A-Za-z0-9_]+)"),
    re.compile(r"from\s+src\.trace_net\.[A-Za-z0-9_.]*?([A-Za-z0-9_]+)\s+import"),
]
VERBS = ("maintenance", "operations", "benchmark")


def bucket(final_path: str) -> str | None:
    parts = final_path.split("/")
    if len(parts) < 3:
        return None
    x = parts[2]
    return parts[3] if x == "pipeline" and len(parts) > 3 else x


def resolve(txt: str, fname: str):
    c = Counter()
    for rx in REFS:
        for m in rx.findall(txt):
            fp = BASE2FINAL.get(m + ".py")
            if fp and bucket(fp):
                c[bucket(fp)] += 1
    if not c:
        # filename fallback: strip verb prefixes / _quality suffix -> module stem
        stem = re.sub(r"^(build|check|run|report|summarize|inspect|update|resolve|apply|list)_", "", Path(fname).stem)
        stem = re.sub(r"_quality$", "", stem)
        for cand in (stem, stem + "_v1"):
            fp = BASE2FINAL.get(cand + ".py")
            if fp and bucket(fp):
                c[bucket(fp)] += 1
                break
    return c.most_common(1)[0][0] if c else None


def main(go: bool):
    scripts = [f.replace("\\", "/") for f in
               subprocess.run(["git", "ls-files", "scripts"], capture_output=True, text=True).stdout.split("\n")
               if f.strip().endswith(".py")]
    rows = []
    for s in scripts:
        parts = s.split("/")
        if len(parts) < 2 or parts[1] not in VERBS:  # only the 3 verb folders; migration/root stay
            continue
        base = Path(s).name
        if base == "__init__.py":
            continue
        stage = resolve(Path(s).read_text(encoding="utf-8", errors="replace"), base)
        if stage is None:
            rows.append((s, s, "unresolved"))
            continue
        target = f"scripts/{parts[1]}/{stage}/{base}"
        rows.append((s, target, stage))

    moves = [(c, p) for c, p, _ in rows if c != p]
    lines = ["# Phase 5-6 scripts stage map", "",
             f"scripts in verb folders: {len(rows)}  to move: {len(moves)}",
             "", "| current | proposed | stage |", "|---|---|---|"]
    for c, p, st in sorted(rows, key=lambda r: r[1]):
        lines.append(f"| `{c}` | `{p}` | {st} |")
    Path("REORG_SCRIPTS_MAP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"scripts: {len(rows)}  to_move: {len(moves)}  unresolved(stay): {sum(1 for c,p,_ in rows if c==p)}")
    print("=== target buckets (counts) ===")
    for leaf, n in sorted(Counter(str(Path(p).parent).replace("\\", "/") for c, p in moves).items()):
        print(f"{n:4d}  {leaf}")
    if not go:
        return 0
    moved = 0
    for c, p in moves:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        rc = subprocess.run(["git", "mv", c, p], capture_output=True, text=True)
        if rc.returncode != 0:
            print("ABORT git mv failed:", c, "->", p, rc.stderr); return 3
        moved += 1
    print(f"moved={moved}")
    # emit the old->new script path map for the reference-updater
    Path("scripts/reorg/_scripts_moved.tsv").write_text(
        "\n".join(f"{c}\t{p}" for c, p in moves), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(go="--go" in sys.argv))
