"""Quality checker for TRACE-Net image OCR figure/callout extractor v1."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MODULE_NAME = "trace_net_image_ocr_figure_callout_extractor_v1_check"
STATUS_CHECKED = "TRACE_NET_IMAGE_OCR_FIGURE_CALLOUT_EXTRACTOR_QUALITY_CHECKED"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def bool_count(records: Sequence[Mapping[str, Any]], key: str) -> int:
    return sum(1 for r in records if bool(r.get(key)))


def evaluate(records: Sequence[Mapping[str, Any]], artifact_quality: str, args: argparse.Namespace) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    summary = {
        "extractor_record_count": len(records),
        "ocr_text_available_count": bool_count(records, "ocr_text_available"),
        "figure_candidate_record_count": sum(1 for r in records if r.get("figure_candidates")),
        "callout_candidate_record_count": sum(1 for r in records if r.get("callout_candidates")),
        "source_trace_ready_count": bool_count(records, "source_trace_ready"),
        "unsafe_record_count": bool_count(records, "unsafe"),
        "answer_permission_count": bool_count(records, "answer_permission"),
        "source_truth_mutation_allowed_count": bool_count(records, "source_truth_mutation_allowed"),
        "write_attempt_count": sum(int(r.get("write_attempt_count") or 0) for r in records),
        "ready_for_visual_linker_v2": artifact_quality == "PASS",
    }
    checks: List[Dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    if args.require_quality_pass:
        add("artifact_quality_pass", artifact_quality == "PASS", artifact_quality, "PASS")
    add("min_extractor_records", summary["extractor_record_count"] >= args.min_extractor_records, summary["extractor_record_count"], f">= {args.min_extractor_records}")
    add("min_ocr_text_available", summary["ocr_text_available_count"] >= args.min_ocr_text_available, summary["ocr_text_available_count"], f">= {args.min_ocr_text_available}")
    add("min_figure_candidate_records", summary["figure_candidate_record_count"] >= args.min_figure_candidate_records, summary["figure_candidate_record_count"], f">= {args.min_figure_candidate_records}")
    add("min_source_trace_ready", summary["source_trace_ready_count"] >= args.min_source_trace_ready, summary["source_trace_ready_count"], f">= {args.min_source_trace_ready}")
    add("max_unsafe", summary["unsafe_record_count"] <= args.max_unsafe, summary["unsafe_record_count"], f"<= {args.max_unsafe}")
    add("max_answer_permission", summary["answer_permission_count"] <= args.max_answer_permission, summary["answer_permission_count"], f"<= {args.max_answer_permission}")
    add("max_source_truth_mutation_allowed", summary["source_truth_mutation_allowed_count"] <= args.max_source_truth_mutation_allowed, summary["source_truth_mutation_allowed_count"], f"<= {args.max_source_truth_mutation_allowed}")
    add("max_write_attempts", summary["write_attempt_count"] <= args.max_write_attempts, summary["write_attempt_count"], f"<= {args.max_write_attempts}")
    return ("PASS" if all(c["passed"] for c in checks) else "FAIL"), checks, summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net image OCR figure/callout extractor v1.")
    p.add_argument("--extractor", required=True)
    p.add_argument("--output", default="")
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--min-extractor-records", type=int, default=1)
    p.add_argument("--min-ocr-text-available", type=int, default=1)
    p.add_argument("--min-figure-candidate-records", type=int, default=0)
    p.add_argument("--min-source-trace-ready", type=int, default=1)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        artifact = read_json(Path(args.extractor))
        records = artifact.get("records") if isinstance(artifact, Mapping) else []
        if not isinstance(records, list):
            records = []
        quality, checks, summary = evaluate([r for r in records if isinstance(r, Mapping)], str(artifact.get("quality_status", "")), args)
        payload = {
            "module_name": MODULE_NAME,
            "status": STATUS_CHECKED,
            "quality_status": quality,
            "created_at_utc": utc_now(),
            "input_extractor": args.extractor,
            "summary": summary,
            "checks": checks,
        }
        if args.output:
            write_json(Path(args.output), payload)
    except Exception as exc:
        print(f"ERROR {MODULE_NAME}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"status={payload.get('status')}")
    print(f"quality_status={payload.get('quality_status')}")
    for key in ("extractor_record_count", "ocr_text_available_count", "figure_candidate_record_count", "callout_candidate_record_count", "source_trace_ready_count", "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count", "write_attempt_count", "ready_for_visual_linker_v2"):
        print(f"{key}={summary.get(key)}")
    return 0 if quality == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
