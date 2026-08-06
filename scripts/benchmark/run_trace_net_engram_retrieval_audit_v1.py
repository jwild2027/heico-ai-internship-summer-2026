#!/usr/bin/env python3
"""Sequential Engram retrieval audit for the RAG project.

The audit records how each question is routed, which Engram skill is selected,
which retrieval tunnels are planned/used, how evidence is bucketed, whether
Self-RAG/CRAG metadata is present, which answer mode is selected, and whether
the final answer passes validation.

It is read-only and sends one request at a time.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

INTERNAL_RE = re.compile(
    r"\b(?:phase\d+(?:_\d+)*_[a-z0-9_()]+|trace_net_[a-z0-9_]+|"
    r"[a-z0-9_]+_removed_\d+_[a-z0-9_()]+)\b",
    re.I,
)
SUPPORTED_SKILLS = {
    "partial_identifier_discovery",
    "exact_identifier_lookup",
    "nomenclature_function_discovery",
    "ata_plus_description_discovery",
    "manufacturer_plus_description_discovery",
}
EXPECTED_ROUTES = {
    "safe_general_chat",
    "exact_identifier_lookup",
    "guided_part_discovery",
    "ata_system_discovery",
    "nomenclature_function_search",
    "exact_table_ipl_lookup",
    "visual_figure_callout_lookup",
    "procedure_task_lookup",
    "warning_caution_note_lookup",
    "authority_eligibility_verification",
    "document_page_navigation",
    "graph_relationship_reasoning",
    "semantic_discovery",
    "cross_source_comparison",
    "contradiction_resolution",
    "ocr_scan_recovery",
    "high_degree_entity_aggregation",
    "multi_question_research",
    "clarification_no_evidence",
}


def compact(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def walk(value: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    yield path, value
    if isinstance(value, Mapping):
        for key, child in value.items():
            next_path = f"{path}.{key}" if path else str(key)
            yield from walk(child, next_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")


def first_by_keys(value: Any, keys: Sequence[str]) -> Any:
    wanted = {key.casefold() for key in keys}
    for path, child in walk(value):
        leaf = path.rsplit(".", 1)[-1].split("[", 1)[0].casefold()
        if leaf in wanted and child not in (None, "", [], {}):
            return child
    return None


def collect_strings(value: Any, keys: Sequence[str]) -> List[str]:
    wanted = {key.casefold() for key in keys}
    output: List[str] = []
    seen = set()
    for path, child in walk(value):
        leaf = path.rsplit(".", 1)[-1].split("[", 1)[0].casefold()
        if leaf not in wanted:
            continue
        candidates: List[str] = []
        if isinstance(child, str):
            candidates = [child]
        elif isinstance(child, list):
            candidates = [str(item) for item in child if isinstance(item, (str, int, float))]
        for item in candidates:
            cleaned = compact(item, 300)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                output.append(cleaned)
    return output


def selected_skill(trace: Mapping[str, Any]) -> tuple[str, str, List[str]]:
    candidates: List[str] = []
    basis = ""
    for path, child in walk(trace):
        if isinstance(child, str) and child in SUPPORTED_SKILLS and child not in candidates:
            candidates.append(child)
        if path.endswith("selection_basis") and isinstance(child, str) and not basis:
            basis = child
    return (candidates[0] if candidates else "", basis, candidates)


def evidence_counts(trace: Mapping[str, Any]) -> Dict[str, int]:
    aliases = {
        "direct": {"direct_evidence", "claim_ready_evidence"},
        "candidate": {"candidate_evidence", "candidates"},
        "semantic": {"semantic_guidance"},
        "visual": {"visual_guidance"},
        "authority": {"authority_evidence"},
        "contradiction": {"contradictions"},
        "source_resolution": {"source_resolution"},
    }
    result = {key: 0 for key in aliases}
    for path, child in walk(trace):
        leaf = path.rsplit(".", 1)[-1].split("[", 1)[0]
        for label, names in aliases.items():
            if leaf in names:
                if isinstance(child, list):
                    result[label] = max(result[label], len(child))
                elif isinstance(child, Mapping):
                    result[label] = max(result[label], len(child))
    return result


def post(url: str, api_key: str, payload: Mapping[str, Any], timeout: float) -> tuple[int, Dict[str, Any], str]:
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
            raw = response.read().decode("utf-8", errors="replace")
            value = json.loads(raw)
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


def extract_answer(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
        message = choices[0].get("message")
        if isinstance(message, Mapping):
            return str(message.get("content") or "")
    return ""


def expected_route_pass(case: Mapping[str, Any], actual: str) -> bool:
    exact = str(case.get("expected_route") or "")
    if exact:
        return actual == exact
    allowed = case.get("expected_route_any")
    return bool(isinstance(allowed, list) and actual in {str(item) for item in allowed})


def build_record(case: Mapping[str, Any], payload: Mapping[str, Any], status: int, error: str, latency: float) -> Dict[str, Any]:
    answer = extract_answer(payload)
    trace = mapping(payload.get("trace_net"))
    route = str(trace.get("route") or "")
    skill, skill_basis, skill_candidates = selected_skill(trace)
    validation = mapping(trace.get("post_answer_validation"))
    counts = evidence_counts(trace)
    planned_tunnels = collect_strings(
        trace,
        ("retrieval_tunnels", "allowed_tunnels", "planned_tunnels"),
    )
    used_tunnels = collect_strings(
        trace,
        ("retrieval_tunnels_used", "executed_tunnels", "tunnels_used"),
    )
    answer_mode_raw = first_by_keys(trace, ("answer_mode", "mode"))
    answer_mode = compact(answer_mode_raw, 500)
    self_rag = first_by_keys(trace, ("self_rag", "self_rag_result", "critic_result"))
    crag = first_by_keys(trace, ("crag_repairs", "crag_result", "repair_records"))
    query_atoms = first_by_keys(trace, ("query_atoms",))
    working_memory = first_by_keys(trace, ("working_memory", "dynamic_working_memory"))
    engram_policy = first_by_keys(trace, ("engram_policy", "compiled_engram_policy"))

    failures: List[str] = []
    kind = str(case.get("kind") or "gate")
    if status != 200:
        failures.append(f"http_status:{status}")
    if kind == "gate" and not expected_route_pass(case, route):
        failures.append(f"route:{route}")
    expected_skill = str(case.get("expected_skill") or "")
    if kind == "gate" and expected_skill and skill != expected_skill:
        failures.append(f"skill:{skill or 'missing'}")
    if kind == "gate" and not validation.get("accepted"):
        failures.append("post_answer_validation_not_accepted")
    if kind == "gate" and not answer.strip():
        failures.append("empty_answer")
    if INTERNAL_RE.search(answer):
        failures.append("internal_diagnostic_leak")
    if answer.lstrip().startswith("{") and '"route"' in answer:
        failures.append("raw_json_public_answer")
    for heading in ("Answer", "Evidence"):
        if kind == "gate" and heading.lower() not in answer.lower():
            failures.append(f"missing_section:{heading}")

    return {
        "id": case.get("id"),
        "kind": kind,
        "coverage": case.get("coverage") or [],
        "question": case.get("question") or "",
        "messages": case.get("messages") or [],
        "expected_route": case.get("expected_route") or "",
        "expected_route_any": case.get("expected_route_any") or [],
        "actual_route": route,
        "expected_skill": expected_skill,
        "selected_skill": skill,
        "skill_selection_basis": skill_basis,
        "skill_candidates": skill_candidates,
        "http_status": status,
        "transport_error": error,
        "latency_seconds": round(latency, 3),
        "validation_accepted": bool(validation.get("accepted")),
        "validation_failures": validation.get("failures") or [],
        "answer_mode": answer_mode,
        "planned_tunnels": planned_tunnels,
        "used_tunnels": used_tunnels,
        "evidence_counts": counts,
        "self_rag_present": self_rag is not None,
        "crag_present": crag is not None,
        "query_atoms_present": query_atoms is not None,
        "working_memory_present": working_memory is not None,
        "engram_policy_present": engram_policy is not None,
        "query_atoms": query_atoms,
        "working_memory": working_memory,
        "engram_policy": engram_policy,
        "post_answer_validation": validation,
        "answer": answer,
        "failures": failures,
        "passed": not failures,
        "raw_response": payload,
    }


def write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "id", "kind", "expected_route", "actual_route", "expected_skill",
        "selected_skill", "skill_selection_basis", "http_status",
        "latency_seconds", "validation_accepted", "answer_mode",
        "planned_tunnels", "used_tunnels", "direct_evidence",
        "candidate_evidence", "semantic_guidance", "visual_guidance",
        "contradictions", "source_resolution", "self_rag_present",
        "crag_present", "working_memory_present", "passed", "failures",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            counts = mapping(record.get("evidence_counts"))
            writer.writerow({
                "id": record.get("id"),
                "kind": record.get("kind"),
                "expected_route": record.get("expected_route") or "|".join(record.get("expected_route_any") or []),
                "actual_route": record.get("actual_route"),
                "expected_skill": record.get("expected_skill"),
                "selected_skill": record.get("selected_skill"),
                "skill_selection_basis": record.get("skill_selection_basis"),
                "http_status": record.get("http_status"),
                "latency_seconds": record.get("latency_seconds"),
                "validation_accepted": record.get("validation_accepted"),
                "answer_mode": record.get("answer_mode"),
                "planned_tunnels": " | ".join(record.get("planned_tunnels") or []),
                "used_tunnels": " | ".join(record.get("used_tunnels") or []),
                "direct_evidence": counts.get("direct", 0),
                "candidate_evidence": counts.get("candidate", 0),
                "semantic_guidance": counts.get("semantic", 0),
                "visual_guidance": counts.get("visual", 0),
                "contradictions": counts.get("contradiction", 0),
                "source_resolution": counts.get("source_resolution", 0),
                "self_rag_present": record.get("self_rag_present"),
                "crag_present": record.get("crag_present"),
                "working_memory_present": record.get("working_memory_present"),
                "passed": record.get("passed"),
                "failures": " | ".join(record.get("failures") or []),
            })


def write_markdown(path: Path, summary: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> None:
    lines = [
        "# Engram Retrieval Audit v1",
        "",
        f"- Quality: **{summary['quality_status']}**",
        f"- Gate cases: **{summary['gate_pass_count']}/{summary['gate_count']} passed**",
        f"- Diagnostic cases recorded: **{summary['diagnostic_count']}**",
        f"- Route coverage: **{summary['route_coverage_count']}/19**",
        f"- Skill coverage: **{summary['skill_coverage_count']}/5**",
        f"- Memory-layer coverage: **{summary['memory_coverage_count']}/6**",
        "",
        "| ID | Kind | Route | Skill | Validation | Latency | Result |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for row in records:
        result = "PASS" if row.get("passed") else "FAIL: " + ", ".join(row.get("failures") or [])
        lines.append(
            f"| {row.get('id')} | {row.get('kind')} | {row.get('actual_route') or '—'} | "
            f"{row.get('selected_skill') or '—'} | {row.get('validation_accepted')} | "
            f"{row.get('latency_seconds')}s | {result} |"
        )
    lines.extend(["", "## Coverage gaps", ""])
    for gap in summary.get("coverage_gaps") or []:
        lines.append(f"- {gap}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--model", default="trace-net-gemma4-cognitive-rag-v1")
    parser.add_argument(
        "--question-bank",
        default="tests/data/trace_net_engram_retrieval_question_bank_v1.json",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    bank = json.loads(Path(args.question_bank).read_text(encoding="utf-8"))
    cases = list(bank.get("cases") or [])
    if args.limit > 0:
        cases = cases[: args.limit]
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records_path = output / "records.jsonl"
    existing: Dict[str, Dict[str, Any]] = {}
    if args.resume and records_path.is_file():
        for line in records_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict) and row.get("id"):
                existing[str(row["id"])] = row

    url = args.base_url.rstrip("/") + "/v1/chat/completions"
    records: List[Dict[str, Any]] = []
    for index, case in enumerate(cases, 1):
        case_id = str(case.get("id") or f"Q{index:03d}")
        if index < args.start_index:
            if case_id in existing:
                records.append(existing[case_id])
            continue
        if args.resume and case_id in existing:
            records.append(existing[case_id])
            print(f"[{index}/{len(cases)}] {case_id} SKIP resume")
            continue

        messages = case.get("messages")
        if not isinstance(messages, list) or not messages:
            messages = [{"role": "user", "content": str(case.get("question") or "")}]
        request_payload = {
            "model": args.model,
            "messages": messages,
            "temperature": 0,
            "stream": False,
        }
        started = time.perf_counter()
        status, payload, error = post(url, args.api_key, request_payload, args.timeout)
        latency = time.perf_counter() - started
        record = build_record(case, payload, status, error, latency)
        records.append(record)

        (output / f"{index:02d}_{case_id}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        with records_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        print(
            f"[{index}/{len(cases)}] {case_id} kind={record['kind']} "
            f"route={record['actual_route'] or 'missing'} "
            f"skill={record['selected_skill'] or 'missing'} "
            f"validation={record['validation_accepted']} "
            f"latency={record['latency_seconds']}s "
            f"pass={record['passed']}"
        )
        if record["failures"]:
            print(f"  failures={record['failures']}")

    by_id = {str(row.get("id")): row for row in records}
    ordered = [by_id[str(case.get("id"))] for case in cases if str(case.get("id")) in by_id]
    gate = [row for row in ordered if row.get("kind") == "gate"]
    diagnostic = [row for row in ordered if row.get("kind") == "diagnostic"]
    route_coverage = {
        str(row.get("actual_route")) for row in ordered if str(row.get("actual_route")) in EXPECTED_ROUTES
    }
    skill_coverage = {
        str(row.get("selected_skill")) for row in ordered if str(row.get("selected_skill")) in SUPPORTED_SKILLS
    }
    memory_coverage = {
        tag.split(":", 1)[1]
        for row in ordered
        for tag in (row.get("coverage") or [])
        if isinstance(tag, str) and tag.startswith("memory:")
    }
    gaps = []
    for route in sorted(EXPECTED_ROUTES - route_coverage):
        gaps.append(f"Missing live route coverage: {route}")
    for skill in sorted(SUPPORTED_SKILLS - skill_coverage):
        gaps.append(f"Missing live Engram skill coverage: {skill}")
    expected_memory = set(bank.get("memory_layers") or [])
    for layer in sorted(expected_memory - memory_coverage):
        gaps.append(f"Missing memory-layer case: {layer}")

    gate_pass_count = sum(bool(row.get("passed")) for row in gate)
    summary = {
        "quality_status": "PASS" if gate and gate_pass_count == len(gate) and not gaps else "FAIL",
        "record_count": len(ordered),
        "gate_count": len(gate),
        "gate_pass_count": gate_pass_count,
        "gate_failure_count": len(gate) - gate_pass_count,
        "diagnostic_count": len(diagnostic),
        "route_coverage_count": len(route_coverage),
        "route_coverage": sorted(route_coverage),
        "skill_coverage_count": len(skill_coverage),
        "skill_coverage": sorted(skill_coverage),
        "memory_coverage_count": len(memory_coverage),
        "memory_coverage": sorted(memory_coverage),
        "coverage_gaps": gaps,
        "failed_gate_ids": [row.get("id") for row in gate if not row.get("passed")],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_csv(output / "retrieval_audit.csv", ordered)
    write_markdown(output / "summary.md", summary, ordered)
    print("=" * 100)
    print(json.dumps(summary, indent=2))
    print(f"output={output}")
    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
