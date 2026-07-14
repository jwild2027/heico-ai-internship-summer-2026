#!/usr/bin/env python3
"""Smoke-test all cognitive routes and optionally the critical live retrieval paths."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ROUTE_EXAMPLES: Tuple[Tuple[str, str], ...] = (
    ("safe_general_chat", "hello"),
    ("exact_identifier_lookup", "Find part 120-41824-003"),
    ("guided_part_discovery", "The P/N contains 41824"),
    ("ata_system_discovery", "I have a part and the ATA number starts with 25"),
    ("nomenclature_function_search", "Find the locking ring near the seat"),
    ("exact_table_ipl_lookup", "Search the IPL table for item 14"),
    ("visual_figure_callout_lookup", "Show the diagram for this component"),
    ("procedure_task_lookup", "How do I remove this assembly?"),
    ("warning_caution_note_lookup", "What warning applies to this task?"),
    ("authority_eligibility_verification", "Is this an approved replacement?"),
    ("document_page_navigation", "Which page discusses the component?"),
    ("graph_relationship_reasoning", "What assembly contains this part?"),
    ("semantic_discovery", "Find pages about corrosion prevention topics"),
    ("cross_source_comparison", "Compare both manuals for the same topic"),
    ("contradiction_resolution", "These two sources disagree and show different numbers"),
    ("ocr_scan_recovery", "The scan is blurry; read the image"),
    ("high_degree_entity_aggregation", "Show every document mentioning this component"),
    ("multi_question_research", "Find part 120-41824-003 and determine whether it is approved"),
    ("clarification_no_evidence", "Can you help me with this?"),
)

LIVE_EXAMPLES: Tuple[Tuple[str, str], ...] = (
    ("safe_general_chat", "hello"),
    ("ata_system_discovery", "I have a part I want to find, ATA number starts with 25"),
    ("exact_identifier_lookup", "Find part 120-41824-003"),
    ("guided_part_discovery", "The P/N contains 41824"),
    ("nomenclature_function_search", "Find the locking ring near the seat"),
)


def post(url: str, api_key: str, query: str, timeout: float) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        value = json.loads(response.read().decode("utf-8", errors="replace"))
        if not isinstance(value, dict):
            raise RuntimeError("response was not a JSON object")
        return value


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8118")
    parser.add_argument("--api-key", default="trace-net-cognitive-local")
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    records: List[Dict[str, Any]] = []
    failures: List[str] = []

    for expected, query in ROUTE_EXAMPLES:
        result = post(args.base_url.rstrip("/") + "/api/trace-net/plan", args.api_key, query, args.timeout_seconds)
        actual = str((result.get("route_plan") or {}).get("primary_route") or "")
        passed = actual == expected
        records.append({
            "mode": "plan",
            "query": query,
            "expected_route": expected,
            "actual_route": actual,
            "passed": passed,
        })
        if not passed:
            failures.append(f"plan:{expected}->{actual}:{query}")

    if args.live:
        for expected, query in LIVE_EXAMPLES:
            result = post(args.base_url.rstrip("/") + "/api/trace-net/ask", args.api_key, query, args.timeout_seconds)
            actual = str(result.get("route") or "")
            content = str(result.get("content") or "")
            critic = result.get("self_rag_critic") if isinstance(result.get("self_rag_critic"), Mapping) else {}
            passed = actual == expected and bool(content) and result.get("source_truth_mutation_allowed") is False
            records.append({
                "mode": "live",
                "query": query,
                "expected_route": expected,
                "actual_route": actual,
                "passed": passed,
                "content_preview": content[:500],
                "critic_quality_status": critic.get("quality_status"),
                "citation_count": result.get("citation_count"),
                "repair_count": len(result.get("crag_repair_attempts") or []),
            })
            if not passed:
                failures.append(f"live:{expected}->{actual}:{query}")

    summary = {
        "quality_status": "PASS" if not failures else "FAIL",
        "record_count": len(records),
        "plan_route_count": len(ROUTE_EXAMPLES),
        "live_route_count": len(LIVE_EXAMPLES) if args.live else 0,
        "failure_count": len(failures),
        "failures": failures,
        "records": records,
    }

    if args.output:
        from pathlib import Path
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if failures:
        raise SystemExit("TRACE_NET_COGNITIVE_ROUTE_SMOKE=FAIL")
    print("TRACE_NET_COGNITIVE_ROUTE_SMOKE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
