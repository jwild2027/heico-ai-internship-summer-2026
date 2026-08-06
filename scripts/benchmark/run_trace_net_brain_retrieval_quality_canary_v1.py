#!/usr/bin/env python3
"""Sequential four-case canary for the observed Engram retrieval failures."""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Mapping

from scripts.benchmark.run_trace_net_engram_retrieval_audit_v1 import selected_skill

INTERNAL_RE = re.compile(
    r"\b(?:phase\d+(?:_\d+)*_[a-z0-9_()]+|"
    r"[a-z0-9_]+_removed_\d+_[a-z0-9_()]+|"
    r"trace_net_[a-z0-9_]+)\b",
    re.I,
)

CASES = (
    {
        "id": "R03_PARTIAL_IDENTIFIER",
        "route": "guided_part_discovery",
        "skill": "partial_identifier_discovery",
        "question": (
            "I only remember that the part number contains 41824. "
            "Show the matching candidates and the source page for each candidate."
        ),
    },
    {
        "id": "R04_ATA_DESCRIPTION",
        "route": "ata_system_discovery",
        "skill": "ata_plus_description_discovery",
        "question": (
            "In ATA 25, find armrest-related parts and cite the strongest "
            "indexed source pages."
        ),
    },
    {
        "id": "R05_NOMENCLATURE_FUNCTION",
        "route": "nomenclature_function_search",
        "skill": "nomenclature_function_discovery",
        "question": (
            "Find a locking ring used near the passenger seat and show "
            "source-backed candidates."
        ),
    },
    {
        "id": "R07_VISUAL_FIGURE",
        "route": "visual_figure_callout_lookup",
        "skill": "",
        "question": (
            "Show the diagram or figure for part 120-41824-003 and cite "
            "the strongest visual source page."
        ),
    },
)


def post(
    url: str,
    api_key: str,
    payload: Mapping[str, Any],
    timeout: float,
) -> tuple[int, Dict[str, Any], str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
            return int(response.status), value if isinstance(value, dict) else {}, ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except Exception:
            value = {"raw": raw}
        return int(exc.code), value if isinstance(value, dict) else {}, f"HTTPError:{exc.code}"
    except Exception as exc:
        return 0, {}, f"{type(exc).__name__}:{exc}"


def answer_text(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
        message = choices[0].get("message")
        if isinstance(message, Mapping):
            return str(message.get("content") or "")
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", default="trace-net-gemma4-cognitive-rag-v1")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    url = args.base_url.rstrip("/") + "/v1/chat/completions"
    records = []

    for index, case in enumerate(CASES, 1):
        started = time.perf_counter()
        status, payload, error = post(
            url,
            args.api_key,
            {
                "model": args.model,
                "messages": [{"role": "user", "content": case["question"]}],
                "temperature": 0,
                "stream": False,
            },
            args.timeout,
        )
        latency = round(time.perf_counter() - started, 3)
        answer = answer_text(payload)
        trace = payload.get("trace_net")
        trace = dict(trace) if isinstance(trace, Mapping) else {}
        route = str(trace.get("route") or "")
        skill, skill_basis, skill_candidates = selected_skill(trace)
        validation = trace.get("post_answer_validation")
        validation = dict(validation) if isinstance(validation, Mapping) else {}
        failures = []

        if status != 200:
            failures.append(f"http_status:{status}")
        if route != case["route"]:
            failures.append(f"route:{route}")
        if case["skill"] and skill != case["skill"]:
            failures.append(f"skill:{skill or 'missing'}")
        if not validation.get("accepted"):
            failures.append("post_answer_validation_not_accepted")
        if INTERNAL_RE.search(answer):
            failures.append("internal_diagnostic_leak")
        if "## Answer" not in answer or "## Evidence" not in answer:
            failures.append("public_sections_missing")

        case_id = case["id"]
        if case_id == "R03_PARTIAL_IDENTIFIER":
            if "Strong full-format candidate" not in answer:
                failures.append("strong_candidate_group_missing")
            if "Irregular or OCR-uncertain match" not in answer:
                failures.append("uncertain_candidate_group_missing")
            strong_pos = answer.find("120-41824-003")
            uncertain_pos = answer.find("120-41824-21")
            if strong_pos < 0 or uncertain_pos < 0 or strong_pos > uncertain_pos:
                failures.append("partial_ranking_not_improved")
        elif case_id == "R04_ATA_DESCRIPTION":
            if "120-20970-001" not in answer or "Structure Armrest" not in answer:
                failures.append("ata_description_match_missing")
        elif case_id == "R05_NOMENCLATURE_FUNCTION":
            if "120-48024-001" not in answer or "Ring Locking" not in answer:
                failures.append("locking_ring_match_missing")
            if "120-36833-001" in answer or "120-36058-001" in answer:
                failures.append("context_only_seat_noise_present")
        elif case_id == "R07_VISUAL_FIGURE":
            for token in (
                "Figure 2 Sheet 1",
                "t_p_120_1176_p000084",
                "strongest visual lead",
            ):
                if token.casefold() not in answer.casefold():
                    failures.append(f"visual_output_missing:{token}")
            if "Directly Supported:" in answer:
                failures.append("empty_visual_placeholder_present")

        record = {
            "id": case_id,
            "question": case["question"],
            "expected_route": case["route"],
            "actual_route": route,
            "expected_skill": case["skill"],
            "selected_skill": skill,
            "skill_selection_basis": skill_basis,
            "skill_candidates": skill_candidates,
            "http_status": status,
            "transport_error": error,
            "latency_seconds": latency,
            "validation": validation,
            "answer": answer,
            "failures": failures,
            "passed": not failures,
            "raw_response": payload,
        }
        records.append(record)
        (output / f"{index:02d}_{case_id}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print("=" * 100)
        print(
            f"[{index}/{len(CASES)}] {case_id} pass={not failures} "
            f"route={route} skill={skill or 'n/a'} latency={latency}s"
        )
        print(f"failures={failures}")
        print(answer)

    pass_count = sum(bool(row["passed"]) for row in records)
    summary = {
        "quality_status": "PASS" if pass_count == len(records) else "FAIL",
        "question_count": len(records),
        "pass_count": pass_count,
        "failure_count": len(records) - pass_count,
        "failed_ids": [row["id"] for row in records if not row["passed"]],
        "records": records,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("=" * 100)
    print(json.dumps(
        {
            key: summary[key]
            for key in (
                "quality_status",
                "question_count",
                "pass_count",
                "failure_count",
                "failed_ids",
            )
        },
        indent=2,
    ))
    print(f"output={output}")
    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
