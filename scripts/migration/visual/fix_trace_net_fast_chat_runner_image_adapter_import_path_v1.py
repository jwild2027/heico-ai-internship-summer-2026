#!/usr/bin/env python3
"""Fix TRACE-Net fast chat runner imports when executed as a direct tiff script.

When running:
    python -B tiff/trace_net_fast_chat_runner_v1.py ...
Python places the tiff/ directory, not the repo root, at sys.path[0]. Any code that imports
`tiff.trace_net_image_route_fast_chat_adapter_v1` can therefore fail even though the adapter
file exists. This patch inserts the repository root into sys.path near the top of the runner.
"""
from __future__ import annotations

import argparse
import ast
import json
import shutil
from pathlib import Path
from typing import Dict, List

STATUS = "TRACE_NET_FAST_CHAT_RUNNER_IMAGE_ADAPTER_IMPORT_PATH_FIX_APPLIED"
MARKER_BEGIN = "# TRACE_NET_IMAGE_ROUTE_IMPORT_PATH_FIX_V1_BEGIN"
MARKER_END = "# TRACE_NET_IMAGE_ROUTE_IMPORT_PATH_FIX_V1_END"
SNIPPET = f'''\n{MARKER_BEGIN}\n# When this file is run directly as `python tiff/trace_net_fast_chat_runner_v1.py`,\n# Python may put only the tiff/ directory on sys.path. Add the repo root so\n# package imports such as `tiff.trace_net_image_route_fast_chat_adapter_v1` work.\ntry:\n    import sys as _trace_net_sys\n    from pathlib import Path as _TraceNetPath\n    _TRACE_NET_REPO_ROOT = _TraceNetPath(__file__).resolve().parents[1]\n    if str(_TRACE_NET_REPO_ROOT) not in _trace_net_sys.path:\n        _trace_net_sys.path.insert(0, str(_TRACE_NET_REPO_ROOT))\nexcept Exception:\n    # Import-path helper must never change runtime safety behavior. If this fails,\n    # the normal module import path/error handling below will still apply.\n    pass\n{MARKER_END}\n'''


def _insert_snippet(text: str) -> tuple[str, bool, str]:
    if MARKER_BEGIN in text and MARKER_END in text:
        return text, False, "already_present"

    lines = text.splitlines(keepends=True)
    insert_at = 0

    # Preserve shebang and coding comment at the very top if present.
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    if len(lines) > insert_at and "coding" in lines[insert_at].lower():
        insert_at += 1

    # Place after module docstring and __future__ imports when possible, but before
    # TRACE-Net package imports. This avoids breaking future imports.
    joined = "".join(lines)
    try:
        module = ast.parse(joined)
        candidates: List[int] = []
        body = list(module.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
            candidates.append(getattr(body[0], "end_lineno", 0))
        for node in body:
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                candidates.append(getattr(node, "end_lineno", 0))
        if candidates:
            insert_at = max(candidates)
    except SyntaxError:
        # The previous syntax-fix patch should have repaired syntax already, but if
        # a user runs this out of order, use the conservative header insertion.
        pass

    new_lines = lines[:insert_at] + [SNIPPET if SNIPPET.endswith("\n") else SNIPPET + "\n"] + lines[insert_at:]
    return "".join(new_lines), True, "inserted_repo_root_sys_path"


def apply_fix(repo_root: Path, require_quality_pass: bool) -> Dict[str, object]:
    target = repo_root / "tiff" / "trace_net_fast_chat_runner_v1.py"
    output_dir = repo_root / "local_data" / "organization" / "trace_net" / "fast_chat_runner_image_adapter_import_path_fix_v1"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_fast_chat_runner_image_adapter_import_path_fix_v1.json"

    failures: List[str] = []
    changed = False
    reason = "not_started"

    if not target.exists():
        failures.append(f"target not found: {target}")
        status = "FAIL"
    else:
        original = target.read_text(encoding="utf-8")
        updated, changed, reason = _insert_snippet(original)
        if changed:
            backup = target.with_suffix(target.suffix + ".pre_image_adapter_import_path_fix_v1.bak")
            if not backup.exists():
                shutil.copy2(target, backup)
            target.write_text(updated, encoding="utf-8")
        try:
            ast.parse(target.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            failures.append(f"syntax error after import path fix: {exc}")
        post = target.read_text(encoding="utf-8")
        if MARKER_BEGIN not in post or "_TRACE_NET_REPO_ROOT" not in post:
            failures.append("repo root sys.path helper marker missing")
        status = "PASS" if not failures else "FAIL"

    report: Dict[str, object] = {
        "status": STATUS,
        "quality_status": status,
        "target": str(target),
        "changed": changed,
        "reason": reason,
        "image_adapter_import_path_fixed": status == "PASS",
        "failure_count": len(failures),
        "failures": failures,
        "safety_contract": {
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"status={STATUS}")
    print(f"quality_status={status}")
    print(f"target={target}")
    print(f"changed={changed}")
    print(f"reason={reason}")
    print(f"image_adapter_import_path_fixed={report['image_adapter_import_path_fixed']}")
    print(f"failure_count={len(failures)}")
    if failures:
        print("failures=" + json.dumps(failures))
    print(f"report={report_path}")

    if require_quality_pass and status != "PASS":
        raise SystemExit(1)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--require-quality-pass", action="store_true")
    args = parser.parse_args()
    apply_fix(Path(args.repo_root).resolve(), args.require_quality_pass)


if __name__ == "__main__":
    main()
