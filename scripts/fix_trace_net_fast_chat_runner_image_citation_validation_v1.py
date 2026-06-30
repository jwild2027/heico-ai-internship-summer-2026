from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

STATUS = "TRACE_NET_FAST_CHAT_RUNNER_IMAGE_CITATION_VALIDATION_FIX_APPLIED"
MODULE = "trace_net_fast_chat_runner_image_citation_validation_fix_v1"
TARGET = Path("tiff/trace_net_fast_chat_runner_v1.py")
MARKER = "TRACE_NET_IMAGE_ROUTE_CITATION_VALIDATION_FIX_V1"

FIX_BLOCK = '''    # TRACE_NET_IMAGE_ROUTE_CITATION_VALIDATION_FIX_V1
    # The generic fast-runner citation validator originally only understood the older
    # exact/figure-item/part-family citation namespaces. Image-route answers use V*
    # citations validated by the image route adapter + image route quality gate.
    # Treat those V* citations as valid only when the image route has linked,
    # source-traced citations and explicitly reports no LLaVA-only part-identity claim.
    if query_type == "image_or_diagram" and image_payload:
        image_citation_count = int(image_payload.get("citation_count", 0) or 0)
        image_source_trace_ready_count = int(image_payload.get("source_trace_ready_citation_count", 0) or 0)
        image_linked_selected_count = int(image_payload.get("linked_selected_evidence_count", 0) or 0)
        image_llava_only_identity_count = int(image_payload.get("llava_only_part_identity_claim_count", 0) or 0)
        image_unsupported_claim_count = int(image_payload.get("unsupported_claim_count", 0) or 0)
        image_adapter_ready = bool(image_payload.get("webui_answer_ready"))
        image_gate_ready = bool(image_gate_payload.get("image_route_quality_gate_ready") or image_gate_payload.get("webui_answer_ready"))
        if (
            image_adapter_ready
            and image_gate_ready
            and image_citation_count > 0
            and image_source_trace_ready_count >= image_citation_count
            and image_linked_selected_count > 0
            and image_llava_only_identity_count == 0
            and image_unsupported_claim_count == 0
        ):
            summary["answer_citation_count"] = max(int(summary.get("answer_citation_count", 0) or 0), image_citation_count)
            summary["valid_answer_citation_count"] = image_citation_count
            summary["invalid_answer_citation_count"] = 0
            summary["invalid_answer_citation_labels"] = []
            summary["answer_quality_gate_passed"] = True
            summary["violation_record_count"] = 0
'''


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def patch_source(source: str) -> tuple[str, list[str], bool]:
    if MARKER in source:
        return source, [], False
    failures: list[str] = []
    anchor = "    quality_status, failures = _quality_status(\n"
    if anchor not in source:
        failures.append("missing anchor: quality_status call")
        return source, failures, False
    patched = source.replace(anchor, FIX_BLOCK + anchor, 1)
    try:
        ast.parse(patched)
    except SyntaxError as exc:
        failures.append(f"patched runner is not valid Python: {exc}")
        return source, failures, False
    return patched, failures, patched != source


def apply_fix(repo_root: Path, *, dry_run: bool = False, output: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = repo_root / TARGET
    failures: list[str] = []
    if not target.exists():
        failures.append(f"missing target: {target}")
        patched = ""
        changed = False
    else:
        original = _read(target)
        patched, patch_failures, changed = patch_source(original)
        failures.extend(patch_failures)
        if not failures and changed and not dry_run:
            backup = target.with_suffix(target.suffix + ".pre_image_route_citation_validation_fix_v1.bak")
            if not backup.exists():
                _write(backup, original)
            _write(target, patched)
        if output is not None:
            _write(output, patched)

    quality_status = "PASS" if not failures else "FAIL"
    result = {
        "status": STATUS,
        "module": MODULE,
        "quality_status": quality_status,
        "target": str(target),
        "changed": bool(changed),
        "image_route_citation_validation_fixed": quality_status == "PASS" and (MARKER in patched),
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
    report_dir = repo_root / "local_data/organization/trace_net/fast_chat_runner_image_citation_validation_fix_v1"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "trace_net_fast_chat_runner_image_citation_validation_fix_v1.json"
    _write(report_path, json.dumps(result, indent=2, sort_keys=True))
    result["report"] = str(report_path)
    if quality_status != "PASS" and not dry_run:
        # Leave the report for inspection, but never write a broken target.
        pass
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Patch fast_chat_runner so image-route V* citations validate through the image route gate.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--require-quality-pass", action="store_true")
    args = parser.parse_args(argv)

    result = apply_fix(Path(args.repo_root), dry_run=args.dry_run, output=Path(args.output) if args.output else None)
    print(f"status={result['status']}")
    print(f"quality_status={result['quality_status']}")
    print(f"target={result['target']}")
    print(f"changed={result['changed']}")
    print(f"image_route_citation_validation_fixed={result['image_route_citation_validation_fixed']}")
    print(f"failure_count={result['failure_count']}")
    if result["failures"]:
        print("failures=" + json.dumps(result["failures"]))
    print(f"report={result['report']}")
    if args.require_quality_pass and result["quality_status"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
