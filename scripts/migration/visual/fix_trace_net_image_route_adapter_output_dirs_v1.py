#!/usr/bin/env python3
"""Patch TRACE-Net image route adapter so nested output dirs are created.

Why this exists:
The fast chat runner calls trace_net_image_route_fast_chat_adapter_v1 with an
output directory such as:
  <smoke>/runner_calls/<slug>/image_route_fast_chat_adapter
When that nested directory does not already exist, the adapter currently reaches
out_path.write_text(...) before creating out_path.parent, causing FileNotFoundError.

This script makes the adapter robust by inserting:
  out_path.parent.mkdir(parents=True, exist_ok=True)
immediately before the canonical out_path.write_text(...) call.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, Dict, List

STATUS = "TRACE_NET_IMAGE_ROUTE_ADAPTER_OUTPUT_DIR_FIX_APPLIED"


def _patch_text(text: str) -> tuple[str, bool, List[str]]:
    failures: List[str] = []
    target = "out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding=\"utf-8\")"
    mkdir_line = "out_path.parent.mkdir(parents=True, exist_ok=True)"

    if target not in text:
        failures.append("missing canonical out_path.write_text target")
        return text, False, failures

    if mkdir_line in text:
        return text, False, failures

    new_text = text.replace(target, f"{mkdir_line}\n    {target}", 1)
    try:
        ast.parse(new_text)
    except SyntaxError as exc:
        failures.append(f"patched adapter syntax invalid: {exc}")
        return text, False, failures
    return new_text, True, failures


def apply_fix(repo_root: Path, require_quality_pass: bool = False) -> Dict[str, Any]:
    target = repo_root / "tiff" / "trace_net_image_route_fast_chat_adapter_v1.py"
    out_dir = repo_root / "local_data" / "organization" / "trace_net" / "image_route_adapter_output_dir_fix_v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "trace_net_image_route_adapter_output_dir_fix_v1.json"

    failures: List[str] = []
    changed = False
    if not target.exists():
        failures.append(f"missing target: {target}")
    else:
        text = target.read_text(encoding="utf-8")
        new_text, changed, patch_failures = _patch_text(text)
        failures.extend(patch_failures)
        if changed:
            backup = target.with_suffix(target.suffix + ".pre_output_dir_fix_v1.bak")
            if not backup.exists():
                backup.write_text(text, encoding="utf-8")
            target.write_text(new_text, encoding="utf-8")
        else:
            # Validate current file even if already patched.
            try:
                ast.parse(target.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                failures.append(f"target syntax invalid: {exc}")

    fixed_text = target.read_text(encoding="utf-8") if target.exists() else ""
    output_dir_fix_present = "out_path.parent.mkdir(parents=True, exist_ok=True)" in fixed_text
    if not output_dir_fix_present:
        failures.append("output directory mkdir guard not present after patch")

    quality_status = "PASS" if not failures else "FAIL"
    report: Dict[str, Any] = {
        "status": STATUS,
        "quality_status": quality_status,
        "target": str(target),
        "changed": changed,
        "image_adapter_output_dir_fix_present": output_dir_fix_present,
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
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"status={STATUS}")
    print(f"quality_status={quality_status}")
    print(f"target={target}")
    print(f"changed={changed}")
    print(f"image_adapter_output_dir_fix_present={output_dir_fix_present}")
    print(f"failure_count={len(failures)}")
    if failures:
        print("failures=" + json.dumps(failures, ensure_ascii=False))
    print(f"report={report_path}")

    if require_quality_pass and quality_status != "PASS":
        raise SystemExit(1)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--require-quality-pass", action="store_true")
    args = parser.parse_args()
    apply_fix(args.repo_root.resolve(), require_quality_pass=args.require_quality_pass)


if __name__ == "__main__":
    main()
