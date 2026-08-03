"""Quality checker for TRACE-Net image visual evidence pack v1."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MODULE_NAME = "trace_net_image_visual_evidence_pack_v1_check"
STATUS_CHECKED = "TRACE_NET_IMAGE_VISUAL_EVIDENCE_PACK_QUALITY_CHECKED"


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


def evaluate(summary: Mapping[str, Any], source_quality: str, args: argparse.Namespace) -> Tuple[str, List[str]]:
    failures: List[str] = []
    if args.require_quality_pass and source_quality != "PASS":
        failures.append("source pack quality_status is not PASS")
    if int(summary.get("visual_evidence_record_count", 0)) < args.min_visual_evidence_records:
        failures.append("visual_evidence_record_count below threshold")
    if int(summary.get("linked_visual_evidence_count", 0)) < args.min_linked_visual_evidence:
        failures.append("linked_visual_evidence_count below threshold")
    if int(summary.get("source_trace_ready_count", 0)) < args.min_source_trace_ready:
        failures.append("source_trace_ready_count below threshold")
    if int(summary.get("citation_ready_count", 0)) < args.min_citation_ready:
        failures.append("citation_ready_count below threshold")
    if int(summary.get("unsafe_record_count", 0)) > args.max_unsafe:
        failures.append("unsafe_record_count above threshold")
    if int(summary.get("answer_permission_count", 0)) > args.max_answer_permission:
        failures.append("answer_permission_count above threshold")
    if int(summary.get("source_truth_mutation_allowed_count", 0)) > args.max_source_truth_mutation_allowed:
        failures.append("source_truth_mutation_allowed_count above threshold")
    if int(summary.get("write_attempt_count", 0)) > args.max_write_attempts:
        failures.append("write_attempt_count above threshold")
    return ("PASS" if not failures else "FAIL"), failures


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack", required=True)
    p.add_argument("--output", default="")
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--min-visual-evidence-records", type=int, default=1)
    p.add_argument("--min-linked-visual-evidence", type=int, default=1)
    p.add_argument("--min-source-trace-ready", type=int, default=1)
    p.add_argument("--min-citation-ready", type=int, default=1)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    pack = read_json(Path(args.pack))
    summary = pack.get("summary", {}) if isinstance(pack, Mapping) else {}
    source_quality = str(pack.get("quality_status", "")) if isinstance(pack, Mapping) else ""
    quality, failures = evaluate(summary, source_quality, args)
    payload = {
        "schema_version": "trace_net_image_visual_evidence_pack_quality_check_v1",
        "module": MODULE_NAME,
        "status": STATUS_CHECKED,
        "quality_status": quality,
        "created_at": utc_now(),
        "source_quality_status": source_quality,
        "summary": summary,
        "checks": {"failures": failures},
    }
    if args.output:
        write_json(Path(args.output), payload)
    print(f"status={STATUS_CHECKED}")
    print(f"quality_status={quality}")
    for key in ("visual_evidence_record_count", "linked_visual_evidence_count", "source_trace_ready_count", "citation_ready_count", "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count", "write_attempt_count", "ready_for_image_diagram_composer"):
        print(f"{key}={summary.get(key)}")
    return 0 if quality == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
