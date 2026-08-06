"""Phase 2 orchestrator — run the remaining reorg stages autonomously.

Per stage (in the given order): git mv every in-scope file (proposed_path under the
stage root, != current) to its locked-map destination, write a re-export shim at the
old path, add __init__.py for new packages, run the affected-subset pytest, auto-fix
the known hardcoded-path pattern, and commit 'reorg: <stage>' iff there are ZERO NEW
failures vs the pre-move baseline. ABORT (no commit, exit non-zero) if a stage shows a
new failure that is NOT the hardcoded-path pattern, or if any deletion appears.

NEVER deletes. `git mv` + added shims/__init__.py only.
"""
from __future__ import annotations
import os
import re
import subprocess
import sys
from pathlib import Path

MAP = Path("REORG_PHASE1_SRC_MAP.md")
REPO = os.getcwd()
_ENV = {**os.environ, "PYTHONPATH": REPO}
SHIM = (
    '"""Compatibility shim (repo reorg — reorg: {stage}). Moved to ``{mod}``.\n\n'
    "Importing from this old path keeps working: it re-exports the relocated module in full.\n"
    'Update imports to the new path when convenient.\n"""\n'
    "import importlib as _importlib\n"
    "import sys as _sys\n"
    '_sys.modules[__name__] = _importlib.import_module("{mod}")\n'
)

# Ordered: (label, proposed-path prefix, pytest -k filter)
STAGES = [
    ("s3_graph_store", "src/trace_net/pipeline/s3_graph_store/",
     "graph or postgres or leiden or community or nha or source_link or rescarta or document_graph or document_organization or entity_trait or org_chart or traceability or traversal"),
    ("s4_embed", "src/trace_net/pipeline/s4_embed/",
     "embed or qdrant or chroma or colpali or bge"),
    ("s5_engram", "src/trace_net/pipeline/s5_engram/",
     "engram or skill or cognitive"),
    ("s6_retrieval", "src/trace_net/pipeline/s6_retrieval/",
     "retriev or router or routing or context or search or rerank or hybrid or rag or query or candidate"),
    ("ingestion", "src/trace_net/ingestion/",
     "ingest or incremental or inventory or part_catalog or part_qa or document_org or manual_grouping or chunk or pdf or answer_context or confidence or page_rout or scan or changed_page or tiff or rag"),
    ("serving", "src/trace_net/serving/",
     "serving or openwebui or api or endpoint or console or adapter or image_route"),
    ("validation", "src/trace_net/validation/",
     "validation or quality or gate or eval or critic or citation or audit or smoke or contract or pipeline"),
    ("visual", "src/trace_net/visual/",
     "visual or vqa or callout or observ or evidence_pack or page_recognition or figure or llava or text_extraction"),
    ("writing", "src/trace_net/writing/",
     "writ or answer or gemma or presentation or renderer or compose or draft or mode or contract"),
]

# Pre-existing reds allowed to persist — measured empirically from the full suite at
# the s2_ocr baseline (scripts/reorg/_baseline_fail.txt / _baseline_err.txt), NOT a
# hand-maintained guess. A stage is green iff it adds nothing beyond these.
BASELINE_FAIL = set(Path("scripts/reorg/_baseline_fail.txt").read_text(encoding="utf-8").split())
ALLOWED_ERROR_FILES = {Path(x).name for x in Path("scripts/reorg/_baseline_err.txt").read_text(encoding="utf-8").split()}


def norm(p):
    return p.replace("\\", "/")


def mod_of(p):
    return norm(p)[:-3].replace("/", ".")


def sh(*a):
    r = subprocess.run(a, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


ROWS = [(norm(c), norm(p)) for c, p in re.findall(r"^\| `([^`]+)` \| `([^`]+)` \|", MAP.read_text(encoding="utf-8"), re.M)]
MOVED_ALL = {c: p for c, p in ROWS if c != p}  # full final old->new map
MOVED_SO_FAR: dict = {}  # grows as stages run; autofix only rewrites to ALREADY-moved paths


def ensure_inits(proposed_paths):
    made = 0
    for p in proposed_paths:
        d = Path(p).parent
        while norm(str(d)).startswith("src/trace_net/") and norm(str(d)) != "src/trace_net":
            ip = d / "__init__.py"
            if not ip.exists():
                ip.write_text("", encoding="utf-8")
                made += 1
            d = d.parent
    return made


def allowed(nodeid):
    return nodeid in BASELINE_FAIL


def run_subset(kw):
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/unit", "-q", "-p", "no:cacheprovider",
                            "--continue-on-collection-errors", "-k", kw, "--tb=no"],
                           capture_output=True, text=True, timeout=900, env=_ENV)
        out = r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return ["__PYTEST_TIMEOUT__"], set(), "pytest timed out after 900s"
    failed = re.findall(r"^FAILED (\S+)", out, re.M)
    errfiles = {Path(m).name for m in re.findall(r"^ERROR (\S+)", out, re.M)}
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    return failed, errfiles, tail


def autofix(test_file):
    """Rewrite any hardcoded old module path in the test to its new location."""
    p = Path(test_file)
    if not p.exists():
        return False
    txt = p.read_text(encoding="utf-8")
    orig = txt
    for old, new in MOVED_SO_FAR.items():
        if old in txt:
            txt = txt.replace(old, new)
    if txt != orig:
        p.write_text(txt, encoding="utf-8")
        return True
    return False


def stage_scope(prefix):
    return [(c, p) for c, p in ROWS if norm(p).startswith(prefix) and c != p]


def run_full():
    """Full-suite run (no -k) for the final reconciliation pass."""
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/unit", "-q", "-p", "no:cacheprovider",
                            "--continue-on-collection-errors", "--tb=no"],
                           capture_output=True, text=True, timeout=1800, env=_ENV)
        out = r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return ["__PYTEST_TIMEOUT__"], set(), "full pytest timed out"
    failed = re.findall(r"^FAILED (\S+)", out, re.M)
    errfiles = {Path(m).name for m in re.findall(r"^ERROR (\S+)", out, re.M)}
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    return failed, errfiles, tail


def main(go, start=0):
    report = []
    # Seed MOVED_SO_FAR with everything already committed before `start`
    # (s2_ocr + any stages preceding the resume point) so autofix can resolve them.
    done_prefixes = ["src/trace_net/pipeline/s2_ocr/"] + [STAGES[i][1] for i in range(start)]
    for c, p in ROWS:
        if c != p and any(norm(p).startswith(dp) for dp in done_prefixes):
            MOVED_SO_FAR[c] = p
    for label, prefix, kw in STAGES[start:]:
        scope = stage_scope(prefix)
        if not go:
            print(f"[{label}] scope={len(scope)} files  prefix={prefix}")
            continue
        # move + shim
        for c, pth in scope:
            Path(pth).parent.mkdir(parents=True, exist_ok=True)
            rc, out = sh("git", "mv", c, pth)
            if rc != 0:
                print(f"ABORT [{label}] git mv failed {c} -> {pth}\n{out}")
                return 3
            Path(c).write_text(SHIM.format(stage=label, mod=mod_of(pth)), encoding="utf-8")
        made = ensure_inits([p for _, p in scope])
        MOVED_SO_FAR.update({c: p for c, p in scope})  # this stage's modules are now moved
        sh("git", "add", "--", *[c for c, _ in scope])
        # add new inits
        rc, out = sh("git", "status", "--porcelain")
        newinits = [l[3:] for l in out.splitlines() if l.endswith("__init__.py") and l[:2].strip() == "??"]
        if newinits:
            sh("git", "add", "--", *newinits)
        # deletion guard
        _, delout = sh("git", "diff", "--cached", "--diff-filter=D", "--name-only")
        if delout.strip():
            print(f"ABORT [{label}] staged deletions detected:\n{delout}")
            return 4
        # pytest + autofix loop
        failed, errfiles, tail = run_subset(kw)
        new = [f for f in failed if not allowed(f)]
        fixed = []
        if new:
            for f in sorted({nf.split("::", 1)[0] for nf in new}):
                if autofix(f):
                    fixed.append(f)
            if fixed:
                sh("git", "add", "--", *fixed)
                failed, errfiles, tail = run_subset(kw)
                new = [f for f in failed if not allowed(f)]
        bad_errs = [e for e in errfiles if e not in ALLOWED_ERROR_FILES]
        if new or bad_errs:
            print(f"ABORT [{label}] NEW failures not covered by known patterns:")
            for f in new:
                print("   FAIL", f)
            for e in bad_errs:
                print("   NEW-ERROR-FILE", e)
            print(f"   (autofixed tests this stage: {fixed})")
            print(f"   pytest tail: {tail}")
            return 5
        # commit
        rc, out = sh("git", "commit", "-q", "-m", f"reorg: {label}\n\n"
                     f"Relocate the {label} stage per REORG_PHASE1_SRC_MAP.md with re-export "
                     f"shims at old paths and __init__.py for new packages. No deletions.\n\n"
                     f"Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
        _, h = sh("git", "rev-parse", "--short", "HEAD")
        report.append((label, len(scope), made, len(fixed), tail.strip(), h.strip()))
        print(f"[{label}] committed {h.strip()}  moved={len(scope)} inits={made} autofixed={len(fixed)}  | {tail.strip()}")

    if go:
        # FINAL RECONCILIATION: after every stage, some cross-cutting tests reference
        # modules that moved in a LATER stage than when the test last ran. Run the FULL
        # suite once, autofix any remaining hardcoded old->new paths (all modules are
        # moved now), re-run, and require zero-new-vs-baseline before committing.
        print("[finalize] full-suite reconciliation ...")
        failed, errfiles, tail = run_full()
        new = [f for f in failed if not allowed(f)]
        fixed = []
        for f in sorted({nf.split("::", 1)[0] for nf in new}):
            if autofix(f):
                fixed.append(f)
        if fixed:
            sh("git", "add", "--", *fixed)
            failed, errfiles, tail = run_full()
            new = [f for f in failed if not allowed(f)]
        bad_errs = [e for e in errfiles if e not in ALLOWED_ERROR_FILES]
        if new or bad_errs:
            print("ABORT [finalize] residual NEW failures after full reconciliation:")
            for f in new:
                print("   FAIL", f)
            for e in bad_errs:
                print("   NEW-ERROR-FILE", e)
            print(f"   pytest tail: {tail}")
            return 6
        _, delout = sh("git", "diff", "--cached", "--diff-filter=D", "--name-only")
        if delout.strip():
            print(f"ABORT [finalize] staged deletions:\n{delout}")
            return 4
        _, staged = sh("git", "diff", "--cached", "--name-only")
        if staged.strip():
            sh("git", "commit", "-q", "-m", "reorg: finalize test paths\n\n"
               "Repo-wide update of tests that load moved modules by hardcoded path to their "
               "final locations (completing the staged move). No deletions.\n\n"
               "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
            _, h = sh("git", "rev-parse", "--short", "HEAD")
            report.append(("finalize", 0, 0, len(fixed), tail.strip(), h.strip()))
            print(f"[finalize] committed {h.strip()}  autofixed={len(fixed)}  | {tail.strip()}")
        else:
            print(f"[finalize] nothing to fix  | {tail.strip()}")

    print("\n==== CONSOLIDATED REPORT ====")
    for label, n, inits, fx, tail, h in report:
        print(f"{h}  reorg: {label:16s} moved={n:3d} shims={n:3d} inits={inits:2d} autofixed_tests={fx}  :: {tail}")
    return 0


if __name__ == "__main__":
    _start = 0
    for a in sys.argv:
        if a.startswith("--start="):
            _start = int(a.split("=", 1)[1])
    raise SystemExit(main(go="--go" in sys.argv, start=_start))
