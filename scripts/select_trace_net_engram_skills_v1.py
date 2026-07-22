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
    load_json,
    select_engram_skills,
)


DEFAULT_SKILLS = (
    "local_data/organization/trace_net/engram_skill_cards_v1/"
    "trace_net_engram_skill_cards_v1.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select inspectable TRACE-Net Engram skills for a query."
    )
    parser.add_argument("--skills", default=DEFAULT_SKILLS)
    parser.add_argument("--query", required=True)
    parser.add_argument("--route", default="")
    parser.add_argument(
        "--query-atoms-json",
        default="",
        help="Optional JSON object or path containing router/query atoms.",
    )
    parser.add_argument("--max-skills", type=int, default=5)
    parser.add_argument("--output", default="")
    return parser


def _load_atoms(value: str):
    text = str(value or "").strip()
    if not text:
        return {}
    path = Path(text)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(text)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    library = load_json(args.skills)
    result = select_engram_skills(
        library,
        query=args.query,
        route=args.route,
        query_atoms=_load_atoms(args.query_atoms_json),
        max_skills=args.max_skills,
    )

    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
