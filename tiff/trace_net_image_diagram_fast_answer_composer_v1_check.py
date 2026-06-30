"""Quality checker for TRACE-Net image/diagram fast answer composer v1."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Tuple

STATUS_CHECKED = "TRACE_NET_IMAGE_DIAGRAM_FAST_ANSWER_COMPOSER_QUALITY_CHECKED"


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


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "ready"}
    return bool(value)


def evaluate(summary: Mapping[str, Any], source_quality: str, args: argparse.Namespace) -> Tuple[str, List[str]]:
    failures: List[str] = []
    if args.require_quality_pass and source_quality != "PASS":
        failures.append("source composer quality_status is not PASS")
    if args.require_webui_answer_ready and not boolish(summary.get("webui_answer_ready")):
        failures.append("webui_answer_ready is false")
    if int(summary.get("citation_count", 0)) < args.min_citations:
        failures.append("citation_count below threshold")
    if int(summary.get("source_trace_ready_citation_count", 0)) < args.min_source_trace_ready_citations:
        failures.append("source_trace_ready_citation_count below threshold")
    if int(summary.get("unsupported_claim_count", 0)) > args.max_unsupported_claims:
        failures.append("unsupported_claim_count above threshold")
    if int(summary.get("llava_only_part_identity_claim_count", 0)) > args.max_llava_only_part_identity_claims:
        failures.append("llava_only_part_identity_claim_count above threshold")
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
    p.add_argument("--composer", required=True)
    p.add_argument("--output", default="")
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-webui-answer-ready", action="store_true")
    p.add_argument("--min-citations", type=int, default=1)
    p.add_argument("--min-source-trace-ready-citations", type=int, default=1)
    p.add_argument("--max-unsupported-claims", type=int, default=0)
    p.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    composer = read_json(Path(args.composer))
    summary = composer.get("summary", {}) if isinstance(composer, Mapping) else {}
    source_quality = str(composer.get("quality_status", "")) if isinstance(composer, Mapping) else ""
    quality, failures = evaluate(summary, source_quality, args)
    payload = {
        "schema_version": "trace_net_image_diagram_fast_answer_composer_quality_check_v1",
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
    for key in ("api_response_status", "citation_count", "source_trace_ready_citation_count", "webui_answer_ready", "unsupported_claim_count", "llava_only_part_identity_claim_count", "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count", "write_attempt_count"):
        print(f"{key}={summary.get(key)}")
    return 0 if quality == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
