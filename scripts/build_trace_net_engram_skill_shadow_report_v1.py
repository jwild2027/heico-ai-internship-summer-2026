#!/usr/bin/env python3
"""Build an offline Phase 2 Engram skill-shadow report from benchmark JSONL."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping

from tiff.trace_net_engram_skill_shadow_v1 import (
    DEFAULT_LIBRARY_PATH,
    build_engram_skill_shadow,
)


def load_records(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f"Invalid JSON on line {line_number}: {exc}"
                ) from exc
            if isinstance(value, dict):
                rows.append(value)
    return rows


def markdown_report(records: List[Mapping[str, Any]]) -> str:
    selected_counts = Counter()
    answer_flags = Counter()
    answer_modes = Counter()
    pass_count = 0
    for row in records:
        shadow = row.get("engram_skill_shadow")
        if not isinstance(shadow, Mapping):
            continue
        if shadow.get("quality_status") == "PASS":
            pass_count += 1
        selected_counts.update(shadow.get("selected_skill_ids") or [])
        answer_flags.update(shadow.get("current_answer_flags") or [])
        answer_modes.update(shadow.get("expected_answer_modes") or [])

    lines = [
        "# TRACE-Net Phase 2 Engram Skill Shadow Report",
        "",
        f"- Records: **{len(records)}**",
        f"- Shadow PASS: **{pass_count}**",
        f"- Shadow FAIL: **{len(records) - pass_count}**",
        "",
        "## Selected skills",
        "",
    ]
    for key, count in selected_counts.most_common():
        lines.append(f"- `{key}`: **{count}**")
    lines += ["", "## Current-answer flags", ""]
    if answer_flags:
        for key, count in answer_flags.most_common():
            lines.append(f"- `{key}`: **{count}**")
    else:
        lines.append("- None")
    lines += ["", "## Expected answer modes", ""]
    for key, count in answer_modes.most_common():
        lines.append(f"- `{key}`: **{count}**")

    for row in records:
        qid = str(row.get("question_id") or "unknown").upper()
        shadow = row.get("engram_skill_shadow")
        if not isinstance(shadow, Mapping):
            shadow = {}
        lines += [
            "",
            "---",
            "",
            f"## {qid}",
            "",
            f"**Question:** {row.get('query') or ''}",
            "",
            f"**Current route:** `{row.get('actual_route') or row.get('route') or ''}`",
            "",
            "**Selected skills:** "
            + (
                ", ".join(
                    f"`{item}`"
                    for item in shadow.get("selected_skill_ids") or []
                )
                or "None"
            ),
            "",
            "**Expected answer modes:** "
            + (
                ", ".join(
                    f"`{item}`"
                    for item in shadow.get("expected_answer_modes") or []
                )
                or "None"
            ),
            "",
            "**Current-answer flags:** "
            + (
                ", ".join(
                    f"`{item}`"
                    for item in shadow.get("current_answer_flags") or []
                )
                or "None"
            ),
            "",
            "### Current answer",
            "",
            str(row.get("answer") or row.get("content") or ""),
            "",
            "### Shadow required first searches",
            "",
        ]
        for item in shadow.get("required_first_searches") or []:
            lines.append(f"- {item}")
        lines += ["", "### Shadow recommendations", ""]
        for item in shadow.get("shadow_recommendations") or []:
            lines.append(f"- {item}")
        lines += ["", "### Shadow guidance", "", "```text"]
        lines.append(str(shadow.get("guidance_text") or ""))
        lines.append("```")
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records_jsonl", type=Path)
    parser.add_argument("--skills", type=Path, default=DEFAULT_LIBRARY_PATH)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--question-id", action="append", default=[])
    parser.add_argument("--max-skills", type=int, default=3)
    args = parser.parse_args(argv)

    rows = load_records(args.records_jsonl)
    selected_ids = {str(item).lower() for item in args.question_id}
    if selected_ids:
        rows = [
            row for row in rows
            if str(row.get("question_id") or "").lower() in selected_ids
        ]
    if args.limit > 0:
        rows = rows[: args.limit]

    output_dir = args.output_dir or (
        args.records_jsonl.parent / "engram_skill_shadow_report"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    augmented: List[Dict[str, Any]] = []
    for row in rows:
        output = dict(row)
        output["engram_skill_shadow"] = build_engram_skill_shadow(
            row,
            query=str(row.get("query") or ""),
            stage="offline_final_record",
            library_path=args.skills,
            max_skills=args.max_skills,
        )
        augmented.append(output)

    jsonl_path = output_dir / "engram_skill_shadow_records.jsonl"
    jsonl_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in augmented
        ),
        encoding="utf-8",
    )
    markdown_path = output_dir / "engram_skill_shadow_report.md"
    markdown_path.write_text(
        markdown_report(augmented),
        encoding="utf-8",
    )

    selected_counts = Counter(
        skill
        for row in augmented
        for skill in (
            row.get("engram_skill_shadow", {}).get("selected_skill_ids") or []
        )
    )
    flag_counts = Counter(
        flag
        for row in augmented
        for flag in (
            row.get("engram_skill_shadow", {}).get("current_answer_flags") or []
        )
    )
    summary = {
        "status": "TRACE_NET_ENGRAM_SKILL_SHADOW_REPORT_V1_DONE",
        "quality_status": (
            "PASS"
            if all(
                row.get("engram_skill_shadow", {}).get("quality_status") == "PASS"
                for row in augmented
            )
            else "FAIL"
        ),
        "record_count": len(augmented),
        "shadow_pass_count": sum(
            row.get("engram_skill_shadow", {}).get("quality_status") == "PASS"
            for row in augmented
        ),
        "selected_skill_counts": dict(selected_counts),
        "current_answer_flag_counts": dict(flag_counts),
        "output_files": {
            "records": str(jsonl_path),
            "report": str(markdown_path),
        },
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
    }
    summary_path = output_dir / "engram_skill_shadow_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    for key in (
        "status",
        "quality_status",
        "record_count",
        "shadow_pass_count",
        "answer_permission",
        "source_truth_mutation_allowed",
        "write_attempt_count",
    ):
        print(f"{key}={summary.get(key)}")
    print(f"records={jsonl_path}")
    print(f"report={markdown_path}")
    print(f"summary={summary_path}")
    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
