#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_engram_skill_cards_v1 import (
    load_and_validate_skill_library,
)


DEFAULT_SKILLS = (
    "local_data/organization/trace_net/engram_skill_cards_v1/"
    "trace_net_engram_skill_cards_v1.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate TRACE-Net Engram Skill Cards v1."
    )
    parser.add_argument("--skills", default=DEFAULT_SKILLS)
    parser.add_argument("--min-cards", type=int, default=5)
    parser.add_argument("--max-cards", type=int, default=40)
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--max-write-attempts", type=int, default=0)
    parser.add_argument("--output", default="")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    library, result = load_and_validate_skill_library(args.skills)

    # Re-run with caller thresholds.
    from tiff.trace_net_engram_skill_cards_v1 import validate_skill_library
    result = validate_skill_library(
        library,
        min_cards=args.min_cards,
        max_cards=args.max_cards,
    )

    failures = list(result.get("errors") or [])
    if args.require_quality_pass and result.get("quality_status") != "PASS":
        failures.append("quality_status_not_pass")
    if args.require_no_answer_permission and result.get("answer_permission"):
        failures.append("answer_permission_true")
    if int(result.get("write_attempt_count") or 0) > args.max_write_attempts:
        failures.append(
            f"write_attempt_count:{result.get('write_attempt_count')}>{args.max_write_attempts}"
        )
    failures = list(dict.fromkeys(failures))
    result["checker_failures"] = failures
    result["checker_quality_status"] = "PASS" if not failures else "FAIL"

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    for key in (
        "status",
        "quality_status",
        "checker_quality_status",
        "skill_card_count",
        "error_count",
        "answer_permission",
        "source_truth_mutation_allowed",
        "can_be_used_as_proof",
        "write_attempt_count",
    ):
        print(f"{key}={result.get(key)}")
    print("skill_ids=" + ",".join(result.get("skill_ids") or []))
    if failures:
        print("failures=" + " | ".join(failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
