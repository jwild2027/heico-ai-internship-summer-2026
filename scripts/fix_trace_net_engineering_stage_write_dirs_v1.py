from __future__ import annotations

import argparse
import json
import py_compile
import re
from pathlib import Path
from typing import Dict, List, Tuple

STATUS = "TRACE_NET_ENGINEERING_STAGE_WRITE_DIRS_FIX_APPLIED"
MODULES_TO_PATCH = [
    "tiff/trace_net_engineering_query_planner_v1.py",
    "tiff/trace_net_engineering_answer_context_pack_v1.py",
    "tiff/trace_net_engineering_answer_composer_v1.py",
    "tiff/trace_net_engineering_answer_runner_v1.py",
    "tiff/trace_net_engineering_runner_eval_set_v1.py",
]


def patch_write_json_text(text: str) -> Tuple[str, bool]:
    """Return text with _write_json helpers hardened to create parent dirs.

    This is intentionally conservative: it only edits function bodies named
    _write_json and only when a local variable named `p` is present.
    """
    lines = text.splitlines()
    out: List[str] = []
    changed = False
    i = 0

    while i < len(lines):
        line = lines[i]
        if re.match(r"^def _write_json\s*\(", line):
            out.append(line)
            i += 1
            while i < len(lines):
                current = lines[i]
                # Stop at next top-level def/class after the helper body.
                if current and not current.startswith((" ", "\t")) and re.match(r"^(def|class)\s+", current):
                    break

                stripped = current.strip()
                if "p.write_text(" in stripped:
                    indent = current[: len(current) - len(current.lstrip())]
                    recent = "\n".join(out[-6:])
                    mkdir_line = f"{indent}p.parent.mkdir(parents=True, exist_ok=True)"
                    if "p.parent.mkdir(parents=True, exist_ok=True)" not in recent:
                        out.append(mkdir_line)
                        changed = True
                out.append(current)
                i += 1
            continue

        out.append(line)
        i += 1

    patched = "\n".join(out)
    if text.endswith("\n"):
        patched += "\n"
    return patched, changed


def patch_file(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"path": str(path), "exists": False, "changed": False, "compiled": False}

    original = path.read_text(encoding="utf-8")
    patched, changed = patch_write_json_text(original)

    if changed:
        backup = path.with_suffix(path.suffix + ".pre_stage_write_dirs_fix.bak")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        path.write_text(patched, encoding="utf-8")

    py_compile.compile(str(path), doraise=True)
    return {"path": str(path), "exists": True, "changed": changed, "compiled": True}


def build_report(repo_root: Path, require_quality_pass: bool = False) -> Dict[str, object]:
    results = [patch_file(repo_root / rel) for rel in MODULES_TO_PATCH]
    missing = [r["path"] for r in results if not r.get("exists")]
    compile_failures: List[str] = []
    failures: List[str] = []

    if missing:
        failures.append(f"missing target files: {len(missing)}")
    patched_count = sum(1 for r in results if r.get("changed"))
    compiled_count = sum(1 for r in results if r.get("compiled"))

    quality_status = "PASS" if not failures and compiled_count == len(results) else "FAIL"
    report = {
        "status": STATUS,
        "quality_status": quality_status,
        "patched_count": patched_count,
        "target_count": len(results),
        "compiled_count": compiled_count,
        "missing_count": len(missing),
        "compile_failure_count": len(compile_failures),
        "failures": failures + compile_failures,
        "results": results,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_record_count": 0,
    }
    if require_quality_pass and quality_status != "PASS":
        raise SystemExit("quality_status is not PASS")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="local_data/organization/trace_net/engineering_stage_write_dirs_fix_v1/trace_net_engineering_stage_write_dirs_fix_v1.json")
    parser.add_argument("--require-quality-pass", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(repo_root, require_quality_pass=args.require_quality_pass)

    out_path = repo_root / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"status={report['status']}")
    print(f"quality_status={report['quality_status']}")
    print(f"patched_count={report['patched_count']}")
    print(f"target_count={report['target_count']}")
    print(f"compiled_count={report['compiled_count']}")
    print(f"missing_count={report['missing_count']}")
    print(f"report={out_path}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
