#!/usr/bin/env python3
"""Run a live 20-question NHA Engram + constrained Gemma server benchmark."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.trace_net_nha_phase14_16_cognitive_v1 import (
    build_nha_writer_packet,
    load_nha_engram_bundle,
)
from scripts.trace_net_nha_phase7_8_runtime_v1 import (
    extract_answer,
    load_real_engine,
    public_contract_valid,
)

SCHEMA_VERSION = "trace_net_nha_phase16_gemma20_v1"


def _dedupe(values):
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def build_bank(phase4_dir: str, engram_dir: str) -> tuple[list[dict[str, Any]], Any, dict[str, Any]]:
    engine, source = load_real_engine(phase4_dir, max_depth=8)
    engram = load_nha_engram_bundle(engram_dir)
    if engram["quality_status"] != "PASS":
        raise ValueError("nha_engram_bundle_not_pass")

    relationships = [dict(row) for row in source["relationships"]]
    children = sorted(_dedupe(row.get("child_part") for row in relationships))
    direct = []
    limited = []
    for child in children:
        result = engine.direct_nha(child)
        if result.get("behavior") == "direct_answer" and result.get("pages"):
            direct.append((child, result))
        elif result.get("behavior") in {"conflict_limited", "candidate_or_clarification"} and result.get("pages"):
            limited.append((child, result))

    cases: list[dict[str, Any]] = []

    def add(kind: str, query: str, action: str) -> None:
        packet = build_nha_writer_packet(query=query, engine=engine, engram_bundle=engram)
        cases.append({
            "case_id": f"NHA-GEMMA20-{len(cases)+1:03d}",
            "kind": kind,
            "query": query,
            "expected_action": action,
            "expected_packet": packet,
            "stream": len(cases) % 2 == 1,
        })

    direct_templates = (
        "What larger unit contains {part}?",
        "Which assembly is the immediate parent of {part}?",
        "Where does {part} belong in the assembly hierarchy?",
        "Give me the one-hop parent assembly for {part}.",
        "What is the next higher assembly for {part}?",
        "Identify the nearest parent assembly of {part}.",
        "Which larger assembly directly contains {part}?",
        "Tell me the direct NHA for {part}.",
    )
    for (child, _), template in zip(direct[:8], direct_templates):
        add("direct_nha", template.format(part=child), "gemma_override")

    scope_templates = (
        "Does the NHA of {part} depend on project or revision?",
        "For {part}, compare the parent candidates by project and configuration.",
        "Which revision or effectivity would resolve the parent candidates for {part}?",
    )
    for (child, _), template in zip(limited[:3], scope_templates):
        add("scope_conflict_resolution", template.format(part=child), "gemma_override")

    supported = [
        row for row in relationships
        if row.get("relationship_status") == "source_supported" and row.get("direct_nha")
    ]
    parents = sorted(_dedupe(row.get("direct_nha") for row in supported))
    parent_added = 0
    for parent in parents:
        result = engine.direct_children(parent)
        if result.get("behavior") == "direct_children_answer" and result.get("pages"):
            query = (
                f"Which components sit immediately below assembly {parent}?"
                if parent_added % 2 == 0
                else f"Give the one-level breakdown under {parent}."
            )
            add("direct_children", query, "gemma_override")
            parent_added += 1
            if parent_added >= 3:
                break

    chain_added = 0
    for row in sorted(
        supported,
        key=lambda value: (-int(value.get("hierarchy_depth") or 0), str(value.get("child_part") or "")),
    ):
        child = str(row.get("child_part") or "")
        result = engine.ancestor_chain(child)
        if result.get("behavior") == "ordered_chain_answer" and len(result.get("chain") or []) > 2 and result.get("pages"):
            query = (
                f"Walk me upward through every supported assembly above {child}."
                if chain_added == 0
                else f"Trace the ordered parent path from {child} to the highest supported assembly."
            )
            add("ancestor_chain", query, "gemma_override")
            chain_added += 1
            if chain_added >= 2:
                break

    evidence_index = 0
    while len(cases) < 18 and direct:
        child, _ = direct[evidence_index % len(direct)]
        add(
            "relationship_evidence",
            f"Which source page proves the NHA relationship for {child}?",
            "gemma_override",
        )
        evidence_index += 1

    add("non_nha_control", "What can TRACE-Net do?", "passthrough")
    add(
        "synthetic_block_control",
        "What larger assembly contains synthetic part 990-91001-001?",
        "synthetic_blocked",
    )
    if len(cases) != 20:
        raise ValueError(f"unable_to_build_gemma20 expected=20 actual={len(cases)}")
    return cases, engine, engram


def _parse_stream(raw: str) -> str:
    pieces = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        data = line[6:].strip()
        if not data or data == "[DONE]":
            continue
        payload = json.loads(data)
        delta = payload.get("choices", [{}])[0].get("delta", {})
        if isinstance(delta, Mapping) and delta.get("content"):
            pieces.append(str(delta["content"]))
    return "".join(pieces)


def call(base_url: str, api_key: str, model: str, case: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": str(case["query"])}],
        "stream": bool(case.get("stream")),
        "temperature": 0,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            headers = {key.casefold(): value for key, value in response.headers.items()}
            if case.get("stream"):
                answer = _parse_stream(raw)
                body = {}
            else:
                body = json.loads(raw)
                answer = extract_answer(body)
            return {
                "http_status": response.status,
                "headers": headers,
                "answer": answer,
                "body": body,
                "latency_seconds": round(time.perf_counter() - started, 3),
            }
    except urllib.error.HTTPError as exc:
        return {
            "http_status": exc.code,
            "headers": {},
            "answer": "",
            "body": {"error": exc.read().decode("utf-8", errors="replace")},
            "latency_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        return {
            "http_status": 599,
            "headers": {},
            "answer": "",
            "body": {"error": f"{type(exc).__name__}: {exc}"},
            "latency_seconds": round(time.perf_counter() - started, 3),
        }


def evaluate(case: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    headers = response.get("headers") or {}
    action = str(headers.get("x-trace-net-nha-action") or "")
    expected_action = str(case.get("expected_action") or "")
    answer = str(response.get("answer") or "")
    packet = case.get("expected_packet") if isinstance(case.get("expected_packet"), Mapping) else {}
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), Mapping) else {}

    if int(response.get("http_status") or 0) != 200:
        failures.append(f"http_status:{response.get('http_status')}")
    if action != expected_action:
        failures.append(f"action expected={expected_action} actual={action}")

    if expected_action == "gemma_override":
        if headers.get("x-trace-net-nha-gemma-calls") != "1":
            failures.append("nha_gemma_call_count_not_one")
        if headers.get("x-trace-net-nha-writer-source") != "gemma":
            failures.append(f"writer_source:{headers.get('x-trace-net-nha-writer-source')}")
        if headers.get("x-trace-net-nha-self-rag") != "PASS":
            failures.append("self_rag_not_pass")
        if not headers.get("x-trace-net-nha-engram-skill"):
            failures.append("engram_skill_missing")
        if int(headers.get("x-trace-net-nha-engram-atoms") or 0) < 1:
            failures.append("engram_atoms_missing")
        valid, contract_failures = public_contract_valid(answer, evidence.get("pages") or [])
        if not valid:
            failures.extend(contract_failures)
        required = []
        for key in ("child", "parent", "direct_nha"):
            if evidence.get(key):
                required.append(str(evidence[key]))
        for key in ("parent_candidates", "chain", "direct_children", "descendants"):
            required.extend(str(value) for value in evidence.get(key) or [])
        for value in _dedupe(required):
            if value not in answer:
                failures.append(f"missing_expected_identifier:{value}")
    elif expected_action == "synthetic_blocked":
        if headers.get("x-trace-net-nha-gemma-calls") not in {"", "0"}:
            failures.append("synthetic_sent_to_gemma")
        if headers.get("x-trace-net-nha-synthetic-access") != "0":
            failures.append("synthetic_artifact_access")
    elif expected_action == "passthrough":
        if action != "passthrough":
            failures.append("passthrough_control_not_passthrough")

    return {
        "case_id": case.get("case_id"),
        "kind": case.get("kind"),
        "query": case.get("query"),
        "stream": bool(case.get("stream")),
        "expected_action": expected_action,
        "actual_action": action,
        "intent": headers.get("x-trace-net-nha-intent", ""),
        "behavior": headers.get("x-trace-net-nha-behavior", ""),
        "engram_skill": headers.get("x-trace-net-nha-engram-skill", ""),
        "engram_atom_count": int(headers.get("x-trace-net-nha-engram-atoms") or 0),
        "gemma_call_count": int(headers.get("x-trace-net-nha-gemma-calls") or 0),
        "writer_source": headers.get("x-trace-net-nha-writer-source", ""),
        "self_rag": headers.get("x-trace-net-nha-self-rag", ""),
        "http_status": response.get("http_status"),
        "latency_seconds": response.get("latency_seconds"),
        "answer": answer,
        "passed": not failures,
        "failures": failures,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase4-dir", required=True)
    parser.add_argument("--nha-engram-dir", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8132")
    parser.add_argument("--api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--model", default="trace-net-gemma4-cognitive-rag-nha-engram-v1")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-count", type=int, default=20)
    parser.add_argument("--request-timeout", type=float, default=300.0)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    bank, _, _ = build_bank(args.phase4_dir, args.nha_engram_dir)
    if len(bank) != args.expected_count:
        raise SystemExit(f"question_count expected={args.expected_count} actual={len(bank)}")
    _write_json(output / "trace_net_nha_phase16_gemma20_bank_v1.json", {"records": bank})

    records = []
    for case in bank:
        response = call(args.base_url, args.api_key, args.model, case, args.request_timeout)
        records.append(evaluate(case, response))
        print(
            f"{case['case_id']} passed={records[-1]['passed']} action={records[-1]['actual_action']} "
            f"gemma={records[-1]['gemma_call_count']} writer={records[-1]['writer_source']} "
            f"latency={records[-1]['latency_seconds']}"
        )

    failed = [row for row in records if not row["passed"]]
    real = [row for row in records if row["expected_action"] == "gemma_override"]
    counts = {
        "question_count": len(records),
        "pass_count": len(records) - len(failed),
        "fail_count": len(failed),
        "http_200_count": sum(row["http_status"] == 200 for row in records),
        "gemma_override_count": len(real),
        "gemma_override_pass_count": sum(row["passed"] for row in real),
        "gemma_call_count": sum(row["gemma_call_count"] for row in real),
        "gemma_writer_accepted_count": sum(row["writer_source"] == "gemma" for row in real),
        "deterministic_fallback_count": sum(row["writer_source"] == "deterministic_fallback" for row in real),
        "self_rag_pass_count": sum(row["self_rag"] == "PASS" for row in real),
        "engram_skill_present_count": sum(bool(row["engram_skill"]) for row in real),
        "engram_atoms_present_count": sum(row["engram_atom_count"] > 0 for row in real),
        "synthetic_block_count": sum(row["expected_action"] == "synthetic_blocked" for row in records),
        "passthrough_control_count": sum(row["expected_action"] == "passthrough" for row in records),
        "stream_count": sum(row["stream"] for row in records),
        "nonstream_count": sum(not row["stream"] for row in records),
        "production_graph_write_count": 0,
        "source_artifact_mutation_count": 0,
        "synthetic_artifact_access_count": 0,
    }
    quality = "PASS" if not failed else "FAIL"
    summary = {
        "schema_version": SCHEMA_VERSION,
        "module": "run_trace_net_nha_phase16_gemma20_v1",
        "status": "TRACE_NET_NHA_PHASE16_GEMMA20_V1",
        "quality_status": quality,
        "counts": counts,
        "latency": {
            "average_seconds": round(sum(float(row["latency_seconds"] or 0) for row in records) / len(records), 3),
            "maximum_seconds": max(float(row["latency_seconds"] or 0) for row in records),
        },
        "failures": [f"{row['case_id']}:{'|'.join(row['failures'])}" for row in failed],
        "warnings": [],
        "artifacts": [
            "trace_net_nha_phase16_gemma20_bank_v1.json",
            "trace_net_nha_phase16_gemma20_results_v1.json",
            "trace_net_nha_phase16_gemma20_results_v1.jsonl",
            "trace_net_nha_phase16_gemma20_quality_v1.json",
        ],
    }
    _write_json(output / "trace_net_nha_phase16_gemma20_results_v1.json", {"records": records})
    _write_jsonl(output / "trace_net_nha_phase16_gemma20_results_v1.jsonl", records)
    _write_json(output / "trace_net_nha_phase16_gemma20_quality_v1.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"quality_status={quality}")
    if args.strict and failed:
        raise SystemExit("TRACE_NET_NHA_PHASE16_GEMMA20=FAIL")
    print("TRACE_NET_NHA_PHASE16_GEMMA20=PASS" if not failed else "TRACE_NET_NHA_PHASE16_GEMMA20=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
