from __future__ import annotations

import argparse
import ast
import json
import shutil
from pathlib import Path

STATUS = "TRACE_NET_FAST_CHAT_RUNNER_IMAGE_ROUTE_SYNTAX_FIX_APPLIED"

BAD_PART = 'if require_part_family_query and summary.get("query_type") != "part_family": failures.append("query_type is not part_family") if require_image_diagram_query and summary.get("query_type") != "image_or_diagram": failures.append("query_type is not image_or_diagram")'
FIX_BLOCK = (
    'if require_part_family_query and summary.get("query_type") != "part_family":\n'
    '        failures.append("query_type is not part_family")\n'
    '    if require_image_diagram_query and summary.get("query_type") != "image_or_diagram":\n'
    '        failures.append("query_type is not image_or_diagram")'
)


def _repair_text(text: str) -> tuple[str, bool, str]:
    if BAD_PART not in text:
        # Already fixed / different shape. Validate that the desired two checks exist.
        if (
            'if require_image_diagram_query and summary.get("query_type") != "image_or_diagram":' in text
            and 'failures.append("query_type is not image_or_diagram")' in text
        ):
            return text, False, "already_fixed_or_anchor_present"
        return text, False, "bad_line_not_found"

    lines = text.splitlines()
    out: list[str] = []
    changed = False
    for line in lines:
        if BAD_PART in line:
            indent = line[: len(line) - len(line.lstrip())]
            out.append(indent + 'if require_part_family_query and summary.get("query_type") != "part_family":')
            out.append(indent + '    failures.append("query_type is not part_family")')
            out.append(indent + 'if require_image_diagram_query and summary.get("query_type") != "image_or_diagram":')
            out.append(indent + '    failures.append("query_type is not image_or_diagram")')
            changed = True
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), changed, "fixed_malformed_inline_if"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair fast chat runner image-route syntax introduced by Patch E integrator.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--target", default="tiff/trace_net_fast_chat_runner_v1.py")
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument(
        "--report",
        default="local_data/organization/trace_net/fast_chat_runner_image_route_syntax_fix_v1/trace_net_fast_chat_runner_image_route_syntax_fix_v1.json",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    target = (repo_root / args.target).resolve()
    report_path = (repo_root / args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    changed = False
    reason = "not_run"

    if not target.exists():
        failures.append(f"target missing: {target}")
    else:
        original = target.read_text(encoding="utf-8")
        repaired, changed, reason = _repair_text(original)
        if changed:
            backup = target.with_suffix(target.suffix + ".pre_image_route_syntax_fix_v1.bak")
            if not backup.exists():
                shutil.copy2(target, backup)
            target.write_text(repaired, encoding="utf-8")
        try:
            ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
        except SyntaxError as exc:
            failures.append(f"syntax error after repair: {exc}")
        if reason == "bad_line_not_found":
            failures.append("malformed line not found and expected image query check anchor is missing")

    quality_status = "PASS" if not failures else "FAIL"
    result = {
        "status": STATUS,
        "quality_status": quality_status,
        "target": str(target.relative_to(repo_root)) if target.exists() else str(target),
        "changed": changed,
        "reason": reason,
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
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(f"status={STATUS}")
    print(f"quality_status={quality_status}")
    print(f"target={result['target']}")
    print(f"changed={changed}")
    print(f"reason={reason}")
    print(f"failure_count={len(failures)}")
    if failures:
        print(f"failures={json.dumps(failures)}")
    print(f"report={report_path.relative_to(repo_root)}")

    if args.require_quality_pass and quality_status != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
