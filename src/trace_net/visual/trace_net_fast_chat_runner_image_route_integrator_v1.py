from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

STATUS = "TRACE_NET_FAST_CHAT_RUNNER_IMAGE_ROUTE_INTEGRATION_APPLIED"
MODULE = "trace_net_fast_chat_runner_image_route_integrator_v1"
TARGET = Path("tiff/trace_net_fast_chat_runner_v1.py")
MARKER = "TRACE_NET_IMAGE_ROUTE_FAST_CHAT_INTEGRATED_V1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _replace_once(text: str, old: str, new: str, failures: List[str], label: str) -> str:
    if old not in text:
        failures.append(f"missing anchor: {label}")
        return text
    return text.replace(old, new, 1)


def _ensure_image_detect_implemented(text: str, failures: List[str]) -> str:
    # Robustly patch the existing image_or_diagram return block in detect_query_type.
    pattern = re.compile(
        r'(if\s+any\(w\s+in\s+q_lower\s+for\s+w\s+in\s+\[[^\]]*?\]\):\s*\n\s*return\s+\{\s*\n\s*"query_type":\s*"image_or_diagram",\s*\n\s*)'
        r'"query_route":\s*"[^"]*",(.*?)'
        r'"implemented_query_type":\s*False,',
        re.DOTALL,
    )
    if '"query_type": "image_or_diagram"' in text and '"query_route": "fast_image_diagram_answer"' in text:
        return text
    m = pattern.search(text)
    if not m:
        failures.append("could not patch image_or_diagram detect_query_type block")
        return text
    replacement = m.group(1) + '"query_route": "fast_image_diagram_answer",' + m.group(2) + '"implemented_query_type": True,'
    return text[:m.start()] + replacement + text[m.end():]



def _ensure_check_image_query_support(text: str, failures: List[str]) -> str:
    """Add --require-image-diagram-query support without depending on exact whitespace."""
    if "require_image_diagram_query" not in text:
        param_pattern = re.compile(r"(require_part_family_query\s*:\s*bool\s*=\s*False\s*,)")
        m = param_pattern.search(text)
        if m:
            text = text[:m.end()] + "\n    require_image_diagram_query: bool = False," + text[m.end():]
        else:
            failures.append("missing anchor: check function require_image_diagram_query arg")
            return text

    if 'query_type is not image_or_diagram' not in text:
        multiline_anchor = '    if require_part_family_query and summary.get("query_type") != "part_family":\n        failures.append("query_type is not part_family")\n'
        validation_multiline = '    if require_image_diagram_query and summary.get("query_type") != "image_or_diagram":\n        failures.append("query_type is not image_or_diagram")\n'
        if multiline_anchor in text:
            text = text.replace(multiline_anchor, multiline_anchor + validation_multiline, 1)
        else:
            compact_pattern = re.compile(
                r'(if\s+require_part_family_query\s+and\s+summary\.get\("query_type"\)\s*!=\s*"part_family"\s*:\s*failures\.append\("query_type is not part_family"\))'
            )
            m = compact_pattern.search(text)
            compact_validation = 'if require_image_diagram_query and summary.get("query_type") != "image_or_diagram": failures.append("query_type is not image_or_diagram")'
            if m:
                text = text[:m.end()] + ' ' + compact_validation + text[m.end():]
            else:
                human_pattern = re.compile(r'(if\s+require_no_human_review_required\s+and)')
                m2 = human_pattern.search(text)
                if m2:
                    text = text[:m2.start()] + compact_validation + ' ' + text[m2.start():]
                else:
                    failures.append("missing anchor: check function image query validation")
                    return text

    if '--require-image-diagram-query' not in text:
        cli_multiline = '    p.add_argument("--require-part-family-query", action="store_true")\n'
        if cli_multiline in text:
            text = text.replace(cli_multiline, cli_multiline + '    p.add_argument("--require-image-diagram-query", action="store_true")\n', 1)
        else:
            compact_cli = re.compile(r'(p\.add_argument\("--require-part-family-query",\s*action="store_true"\))')
            m = compact_cli.search(text)
            if m:
                text = text[:m.end()] + ' p.add_argument("--require-image-diagram-query", action="store_true")' + text[m.end():]
            else:
                failures.append("missing anchor: check CLI image query flag")
                return text
    return text

def integrate_source_text(source: str) -> Tuple[str, List[str], bool]:
    """Return patched fast_chat_runner source, failures, changed.

    This intentionally uses small anchored source edits instead of rewriting the whole runner.
    It preserves the existing exact part, figure/item, and part-family routes while enabling
    image_or_diagram through the Patch D adapter and image quality gate.
    """
    if MARKER in source:
        return source, [], False

    failures: List[str] = []
    text = source

    text = _ensure_image_detect_implemented(text, failures)

    # Build function argument so the runner can receive Patch C/D evidence.
    old_sig = "    require_webui_answer_ready: bool = False,\n    quality: bool = False,\n) -> dict[str, Any]:"
    new_sig = "    require_webui_answer_ready: bool = False,\n    image_visual_evidence_pack: str | None = None,\n    quality: bool = False,\n) -> dict[str, Any]:"
    if "image_visual_evidence_pack: str | None = None" not in text:
        text = _replace_once(text, old_sig, new_sig, failures, "build_fast_chat_runner image_visual_evidence_pack arg")

    image_branch = '''    elif query_type == "image_or_diagram":
        comp_dir = out_dir / "image_route_fast_chat_adapter"
        comp_dir.mkdir(parents=True, exist_ok=True)
        if not image_visual_evidence_pack:
            comp_payload = {
                "quality_status": "FAIL",
                "answer": "TRACE-Net recognized this as an image_or_diagram query, but no image visual evidence pack was supplied. No answer is produced from unvalidated visual evidence.",
                "citations": [],
                "summary": {
                    "route_type": "image_or_diagram",
                    "webui_answer_ready": False,
                    "citation_count": 0,
                    "source_trace_ready_citation_count": 0,
                    "linked_selected_evidence_count": 0,
                    "unsupported_claim_count": 0,
                    "llava_only_part_identity_claim_count": 0,
                    "unsafe_record_count": 0,
                    "answer_permission_count": 0,
                    "source_truth_mutation_allowed_count": 0,
                    "write_attempt_count": 0,
                },
            }
        else:
            builder = _load_builder(
                "tiff.trace_net_image_route_fast_chat_adapter_v1",
                ["build_adapter", "build_image_route_fast_chat_adapter", "build_trace_net_image_route_fast_chat_adapter"],
            )
            if not builder:
                raise RuntimeError("image route adapter module is not available")
            result = _invoke_builder(builder, {
                "image_visual_evidence_pack": image_visual_evidence_pack,
                "question": question,
                "output_dir": str(comp_dir),
                "require_webui_answer_ready": require_webui_answer_ready,
                "min_citations": 1 if require_webui_answer_ready else 0,
                "min_source_trace_ready_citations": 1 if require_webui_answer_ready else 0,
                "max_unsupported_claims": 0,
                "max_llava_only_part_identity_claims": 0,
                "max_unsafe": 0,
                "max_answer_permission": 0,
                "max_source_truth_mutation_allowed": 0,
                "max_write_attempts": 0,
            })
            comp_report = comp_dir / "trace_net_image_route_fast_chat_adapter_v1.json"
            comp_payload = _read_json(comp_report) if comp_report.exists() else (result if isinstance(result, dict) else {})
        stage_payloads["image_route_fast_chat_adapter"] = comp_payload
        stage_reports["image_route_fast_chat_adapter"] = comp_payload.get("quality_status", "UNKNOWN")
        stage_paths["image_route_fast_chat_adapter"] = str(comp_dir / "trace_net_image_route_fast_chat_adapter_v1.json")
        answer_text = comp_payload.get("answer") or comp_payload.get("answer_text") or ""
        _write_text(out_dir / f"{MODULE}_answer.md", answer_text)

        gate_builder = _load_builder(
            "tiff.trace_net_image_route_multi_route_quality_gate_v1",
            ["evaluate_gate"],
        )
        if gate_builder:
            gate_payload = _invoke_builder(gate_builder, {
                "adapter": comp_payload,
                "require_webui_answer_ready": require_webui_answer_ready,
                "min_citations": 1 if require_webui_answer_ready else 0,
                "min_source_trace_ready_citations": 1 if require_webui_answer_ready else 0,
                "max_unsupported_claims": 0,
                "max_llava_only_part_identity_claims": 0,
                "max_unsafe": 0,
                "max_answer_permission": 0,
                "max_source_truth_mutation_allowed": 0,
                "max_write_attempts": 0,
            })
            gate_dir = out_dir / "image_route_multi_route_quality_gate"
            gate_dir.mkdir(parents=True, exist_ok=True)
            gate_path = gate_dir / "trace_net_image_route_multi_route_quality_gate_v1.json"
            _write_json(gate_path, gate_payload)
            stage_payloads["image_route_multi_route_quality_gate"] = gate_payload
            stage_reports["image_route_multi_route_quality_gate"] = gate_payload.get("quality_status", "UNKNOWN")
            stage_paths["image_route_multi_route_quality_gate"] = str(gate_path)
'''

    if 'elif query_type == "image_or_diagram":' not in text:
        text = _replace_once(text, '    elif query_type == "figure_or_item"', image_branch + '    elif query_type == "figure_or_item"', failures, "insert image_or_diagram route branch")

    old_payloads = '    fam_payload = stage_payloads.get("part_family_fast_answer_composer", {}).get("summary", {})\n'
    new_payloads = old_payloads + '    image_payload = stage_payloads.get("image_route_fast_chat_adapter", {}).get("summary", {})\n    image_gate_payload = stage_payloads.get("image_route_multi_route_quality_gate", {}).get("summary", {})\n'
    if 'image_payload = stage_payloads.get("image_route_fast_chat_adapter"' not in text:
        text = _replace_once(text, old_payloads, new_payloads, failures, "image payload summary variables")

    old_ready = '    elif query_type == "part_family":\n        route_ready = bool(fam_payload.get("part_family_fast_answer_ready"))\n'
    new_ready = old_ready + '    elif query_type == "image_or_diagram":\n        route_ready = bool(image_payload.get("webui_answer_ready")) and int(image_payload.get("source_trace_ready_citation_count", 0) or 0) > 0\n'
    if 'elif query_type == "image_or_diagram":\n        route_ready = bool(image_payload.get("webui_answer_ready"))' not in text:
        text = _replace_once(text, old_ready, new_ready, failures, "image route readiness")

    old_summary_fields = '        "part_family_fast_answer_ready": bool(fam_payload.get("part_family_fast_answer_ready")),\n'
    new_summary_fields = old_summary_fields + '''        "image_route_fast_chat_ready": bool(image_payload.get("webui_answer_ready")),
        "image_route_citation_count": int(image_payload.get("citation_count", 0) or 0),
        "image_route_source_trace_ready_citation_count": int(image_payload.get("source_trace_ready_citation_count", 0) or 0),
        "image_route_linked_selected_evidence_count": int(image_payload.get("linked_selected_evidence_count", 0) or 0),
        "image_route_llava_only_part_identity_claim_count": int(image_payload.get("llava_only_part_identity_claim_count", 0) or 0),
'''
    if '"image_route_fast_chat_ready"' not in text:
        text = _replace_once(text, old_summary_fields, new_summary_fields, failures, "image route summary fields")

    # Do not run the old generic multi-route gate for image_or_diagram. Patch D provides route-specific gate.
    if 'if run_multi_route_quality_gate and query_type != "image_or_diagram":' not in text:
        text = _replace_once(text, '    if run_multi_route_quality_gate:\n', '    if run_multi_route_quality_gate and query_type != "image_or_diagram":\n', failures, "skip generic gate for image route")

    image_gate_summary_block = '''    if query_type == "image_or_diagram" and image_gate_payload:
        summary["multi_route_quality_gate_passed"] = bool(image_gate_payload.get("image_route_quality_gate_ready"))
        summary["webui_answer_ready"] = bool(image_gate_payload.get("webui_answer_ready"))
        summary["multi_route_quality_report"] = stage_paths.get("image_route_multi_route_quality_gate")
        summary["route_quality_status"] = stage_payloads.get("image_route_multi_route_quality_gate", {}).get("quality_status")
        summary["route_check_count"] = len((stage_payloads.get("image_route_multi_route_quality_gate", {}) or {}).get("checks", {}) or {})
        summary["route_check_fail_count"] = sum(1 for v in ((stage_payloads.get("image_route_multi_route_quality_gate", {}) or {}).get("checks", {}) or {}).values() if not v)
        summary["stage_count"] = len(summary["stage_quality_statuses"])
'''
    anchor = '    quality_status, failures = _quality_status(\n'
    if 'if query_type == "image_or_diagram" and image_gate_payload:' not in text:
        text = _replace_once(text, anchor, image_gate_summary_block + anchor, failures, "image gate summary transfer")

    # CLI wiring.
    if 'p.add_argument("--image-visual-evidence-pack")' not in text:
        text = _replace_once(text, '    p.add_argument("--context-pack", required=True)\n', '    p.add_argument("--context-pack", required=True)\n    p.add_argument("--image-visual-evidence-pack")\n', failures, "CLI image visual evidence pack argument")
    if 'image_visual_evidence_pack=args.image_visual_evidence_pack,' not in text:
        text = _replace_once(text, '        require_webui_answer_ready=args.require_webui_answer_ready,\n        quality=args.quality,\n', '        require_webui_answer_ready=args.require_webui_answer_ready,\n        image_visual_evidence_pack=args.image_visual_evidence_pack,\n        quality=args.quality,\n', failures, "CLI build function image evidence pack pass-through")

    # Check CLI requirement for image query. Current repo revisions sometimes keep
    # the check function/CLI in compact one-line source, so use tolerant regex edits.
    text = _ensure_check_image_query_support(text, failures)

    text = text + f'\n# {MARKER}: image_or_diagram route integrated through Patch D adapter and image route quality gate.\n'
    return text, failures, text != source


def apply_integration(repo_root: Path, *, dry_run: bool = False, output: Path | None = None) -> Dict[str, Any]:
    target = repo_root / TARGET
    failures: List[str] = []
    if not target.exists():
        failures.append(f"target file not found: {target}")
        result = _result(failures, False, dry_run, target, output)
        return result
    original = _read(target)
    patched, patch_failures, changed = integrate_source_text(original)
    failures.extend(patch_failures)
    if not failures and changed and not dry_run:
        backup = target.with_suffix(target.suffix + ".pre_image_route_integration_v1.bak")
        if not backup.exists():
            _write(backup, original)
        _write(target, patched)
    elif dry_run and output:
        _write(output, patched)
    return _result(failures, changed, dry_run, target, output)


def _result(failures: List[str], changed: bool, dry_run: bool, target: Path, output: Path | None) -> Dict[str, Any]:
    quality_status = "PASS" if not failures else "FAIL"
    summary = {
        "target": str(target),
        "dry_run": dry_run,
        "changed": changed,
        "failure_count": len(failures),
        "image_route_fast_chat_runner_integrated": quality_status == "PASS",
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": 0 if dry_run else (1 if changed and quality_status == "PASS" else 0),
    }
    return {
        "status": STATUS,
        "quality_status": quality_status,
        "module": MODULE,
        "summary": summary,
        "failures": failures,
        "output": str(output) if output else None,
    }


def _parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--output")
    p.add_argument("--report-output", default="local_data/organization/trace_net/fast_chat_runner_image_route_integration_v1/trace_net_fast_chat_runner_image_route_integration_v1.json")
    p.add_argument("--require-quality-pass", action="store_true")
    return p.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(argv)
    result = apply_integration(Path(args.repo_root), dry_run=args.dry_run, output=Path(args.output) if args.output else None)
    report = Path(args.report_output)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    s = result["summary"]
    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    print(f"target={s['target']}")
    print(f"changed={s['changed']}")
    print(f"image_route_fast_chat_runner_integrated={s['image_route_fast_chat_runner_integrated']}")
    print(f"failure_count={s['failure_count']}")
    if result["failures"]:
        print("failures=" + json.dumps(result["failures"], ensure_ascii=False))
    print(f"report={report}")
    if args.require_quality_pass and result["quality_status"] != "PASS":
        return 1
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
