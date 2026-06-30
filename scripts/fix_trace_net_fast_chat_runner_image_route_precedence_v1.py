from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, List, Tuple

STATUS = "TRACE_NET_FAST_CHAT_RUNNER_IMAGE_ROUTE_PRECEDENCE_FIX_APPLIED"
MODULE = "trace_net_fast_chat_runner_image_route_precedence_fix_v1"
TARGET = Path("tiff/trace_net_fast_chat_runner_v1.py")
MARKER = "TRACE_NET_IMAGE_ROUTE_PRECEDENCE_FIX_V1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def patch_source_text(source: str) -> Tuple[str, List[str], bool]:
    """Route figure-only visual questions to image_or_diagram when image evidence is supplied.

    The existing runner correctly treats figure+item queries as figure_or_item. But a question like
    "What does figure 69 show?" has a figure number and no item/callout, so it should use the
    image/diagram evidence route when --image-visual-evidence-pack is present.
    """
    if MARKER in source:
        return source, [], False

    failures: List[str] = []
    if "image_visual_evidence_pack" not in source:
        failures.append("image_visual_evidence_pack argument not found; run Patch E integration first")
    if 'elif query_type == "image_or_diagram"' not in source:
        failures.append("image_or_diagram route branch not found; run Patch D/E integration first")

    if failures:
        return source, failures, False

    old = '    query_plan = detect_query_type(question, part_number=part_number, part_family=part_family, figure=figure, item=item)\n    query_type = query_plan["query_type"]\n'
    new = '''    query_plan = detect_query_type(question, part_number=part_number, part_family=part_family, figure=figure, item=item)
    # TRACE_NET_IMAGE_ROUTE_PRECEDENCE_FIX_V1:
    # Figure-only visual questions such as "What does figure 69 show?" must use
    # the image_or_diagram route when an image visual evidence pack is supplied.
    # Figure+item questions remain figure_or_item.
    if (
        image_visual_evidence_pack
        and query_plan.get("query_type") == "figure_or_item"
        and query_plan.get("figure")
        and not query_plan.get("item")
    ):
        _q_lower = (question or "").lower()
        _asks_for_visual_figure = any(
            token in _q_lower
            for token in [
                "show",
                "shows",
                "showing",
                "diagram",
                "image",
                "visual",
                "picture",
                "depict",
                "depicts",
                "look like",
            ]
        )
        if _asks_for_visual_figure:
            query_plan = dict(query_plan)
            query_plan["query_type"] = "image_or_diagram"
            query_plan["query_route"] = "fast_image_diagram_answer"
            query_plan["implemented_query_type"] = True
    query_type = query_plan["query_type"]
'''
    if old not in source:
        failures.append("query_plan/query_type assignment anchor not found")
        return source, failures, False

    patched = source.replace(old, new, 1)
    try:
        ast.parse(patched)
    except SyntaxError as exc:
        failures.append(f"patched runner is not valid Python: {exc}")
        return source, failures, False
    return patched, failures, patched != source


def apply_fix(repo_root: Path, *, dry_run: bool = False, output: Path | None = None) -> dict[str, Any]:
    target = repo_root / TARGET
    failures: List[str] = []
    changed = False
    if not target.exists():
        failures.append(f"target not found: {target}")
        return _result(target, failures, changed, dry_run, output)

    original = _read(target)
    patched, patch_failures, changed = patch_source_text(original)
    failures.extend(patch_failures)

    if not failures and changed and not dry_run:
        backup = target.with_suffix(target.suffix + ".pre_image_route_precedence_fix_v1.bak")
        if not backup.exists():
            _write(backup, original)
        _write(target, patched)
    elif not failures and dry_run and output:
        _write(output, patched)
    return _result(target, failures, changed, dry_run, output)


def _result(target: Path, failures: List[str], changed: bool, dry_run: bool, output: Path | None) -> dict[str, Any]:
    quality_status = "PASS" if not failures else "FAIL"
    return {
        "status": STATUS,
        "quality_status": quality_status,
        "module": MODULE,
        "summary": {
            "target": str(target),
            "changed": changed,
            "dry_run": dry_run,
            "output": str(output) if output else None,
            "image_route_precedence_fixed": quality_status == "PASS",
            "failure_count": len(failures),
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0 if dry_run else (1 if changed and quality_status == "PASS" else 0),
        },
        "failures": failures,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--output")
    p.add_argument("--report-output", default="local_data/organization/trace_net/fast_chat_runner_image_route_precedence_fix_v1/trace_net_fast_chat_runner_image_route_precedence_fix_v1.json")
    p.add_argument("--require-quality-pass", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = apply_fix(Path(args.repo_root), dry_run=args.dry_run, output=Path(args.output) if args.output else None)
    report = Path(args.report_output)
    report.parent.mkdir(parents=True, exist_ok=True)
    _write(report, json.dumps(result, indent=2, sort_keys=True))
    s = result["summary"]
    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    print(f"target={s['target']}")
    print(f"changed={s['changed']}")
    print(f"image_route_precedence_fixed={s['image_route_precedence_fixed']}")
    print(f"failure_count={s['failure_count']}")
    if result["failures"]:
        print("failures=" + json.dumps(result["failures"], ensure_ascii=False))
    print(f"report={report}")
    if args.require_quality_pass and result["quality_status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
