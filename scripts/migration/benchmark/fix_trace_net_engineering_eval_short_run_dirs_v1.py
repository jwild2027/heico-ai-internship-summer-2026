from __future__ import annotations

import argparse
import json
import py_compile
from pathlib import Path
from typing import Any, Dict

STATUS = "TRACE_NET_ENGINEERING_EVAL_SHORT_RUN_DIRS_FIX_APPLIED"
TARGET = Path("tiff/trace_net_engineering_runner_eval_set_v1.py")

HELPER = '''\n\ndef _eval_run_task_hint(question: str) -> str:\n    """Return a short stable hint for H6 eval run folders.\n\n    The full question remains inside the JSON record; the folder name is kept\n    intentionally short to avoid Windows MAX_PATH failures in nested stage\n    outputs such as trace_net_engineering_answer_context_pack_v1_quality_check.json.\n    """\n    q = str(question or "").lower()\n    if "why" in q or "missing" in q or "fail" in q or "error" in q:\n        return "debug"\n    if "compare" in q:\n        return "compare"\n    if "part number" in q or "find part" in q:\n        return "part"\n    if "figure" in q or "diagram" in q or "show" in q:\n        return "fig"\n    return "q"\n'''

OLD_LINE = 'run_dir = runs_dir / f"q{idx:02d}_{_slug(question)}"'
NEW_BLOCK = '''question_hash = hashlib.sha1(str(question or "").encode("utf-8")).hexdigest()[:8]\n        task_hint = _eval_run_task_hint(str(question or ""))\n        run_dir = runs_dir / f"q{idx:02d}_{task_hint}_{question_hash}"\n        run_dir.mkdir(parents=True, exist_ok=True)'''


def _insert_import(text: str) -> str:
    if "import hashlib" in text:
        return text
    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            insert_at = i + 1
        elif insert_at and line.strip() and not line.startswith("#"):
            break
    lines.insert(insert_at, "import hashlib")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _insert_helper(text: str) -> str:
    if "def _eval_run_task_hint(" in text:
        return text
    marker = "def _slug("
    idx = text.find(marker)
    if idx == -1:
        # Insert before threshold args as a safe fallback.
        fallback = "def _add_threshold_args("
        fidx = text.find(fallback)
        if fidx == -1:
            raise ValueError("Could not locate _slug or _add_threshold_args insertion point")
        return text[:fidx] + HELPER + "\n" + text[fidx:]

    # Find the end of the _slug function by locating the next top-level def.
    next_def = text.find("\ndef ", idx + len(marker))
    if next_def == -1:
        raise ValueError("Could not locate end of _slug function")
    return text[:next_def] + HELPER + text[next_def:]


def patch_text(text: str) -> tuple[str, Dict[str, Any]]:
    original = text
    text = _insert_import(text)
    text = _insert_helper(text)

    replacements = 0
    if OLD_LINE in text:
        text = text.replace(OLD_LINE, NEW_BLOCK)
        replacements += 1
    elif "_eval_run_task_hint" in text and "hashlib.sha1" in text and "run_dir.mkdir(parents=True, exist_ok=True)" in text:
        # Already patched.
        pass
    else:
        raise ValueError("Could not find eval run_dir slug line to replace")

    changed = text != original
    return text, {
        "changed": changed,
        "replacement_count": replacements,
        "short_run_dir_helper_present": "def _eval_run_task_hint(" in text,
        "hash_run_dir_present": "hashlib.sha1" in text and "task_hint" in text,
        "legacy_long_slug_line_present": OLD_LINE in text,
        "run_dir_mkdir_present": "run_dir.mkdir(parents=True, exist_ok=True)" in text,
    }


def apply_fix(repo_root: Path, require_quality_pass: bool = False) -> Dict[str, Any]:
    repo_root = Path(repo_root)
    target = repo_root / TARGET
    failures: list[str] = []
    if not target.exists():
        failures.append(f"missing target: {target}")
        result = {
            "status": STATUS,
            "quality_status": "FAIL",
            "target": str(target),
            "changed": False,
            "failures": failures,
            "failure_count": len(failures),
        }
        if require_quality_pass:
            raise SystemExit(json.dumps(result, indent=2))
        return result

    old = target.read_text(encoding="utf-8")
    backup = target.with_suffix(target.suffix + ".pre_short_eval_run_dirs.bak")
    backup.write_text(old, encoding="utf-8")

    try:
        new, details = patch_text(old)
        target.write_text(new, encoding="utf-8")
        py_compile.compile(str(target), doraise=True)
    except Exception as exc:
        target.write_text(old, encoding="utf-8")
        failures.append(f"patch_failed: {type(exc).__name__}: {exc}")
        details = {}

    # Verify expected postconditions from the current target contents.
    final = target.read_text(encoding="utf-8")
    if OLD_LINE in final:
        failures.append("legacy long-slug run_dir line still present")
    if "def _eval_run_task_hint(" not in final:
        failures.append("short task-hint helper missing")
    if "hashlib.sha1" not in final:
        failures.append("question hash missing")
    if "run_dir.mkdir(parents=True, exist_ok=True)" not in final:
        failures.append("explicit run_dir mkdir missing")

    result = {
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "target": str(target),
        "backup": str(backup),
        "changed": bool(details.get("changed")),
        "details": details,
        "failure_count": len(failures),
        "failures": failures,
        "safety_contract": {
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
        },
    }

    report_dir = repo_root / "local_data/organization/trace_net/engineering_eval_short_run_dirs_fix_v1"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "trace_net_engineering_eval_short_run_dirs_fix_v1.json"
    report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["report"] = str(report_path)

    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    print(f"target={result['target']}")
    print(f"changed={result['changed']}")
    print(f"failure_count={result['failure_count']}")
    print(f"report={result['report']}")

    if require_quality_pass and result["quality_status"] != "PASS":
        raise SystemExit(1)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch H6 eval run directories to short Windows-safe names")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--require-quality-pass", action="store_true")
    args = parser.parse_args()
    apply_fix(Path(args.repo_root), require_quality_pass=args.require_quality_pass)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
