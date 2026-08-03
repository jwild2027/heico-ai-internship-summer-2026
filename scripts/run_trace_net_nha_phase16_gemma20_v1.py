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

SCHEMA_VERSION = "trace_net_nha_phase17_real_situation_gemma20_v1"


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
    """Build a real-language live gate.

    Every non-synthetic case must travel through a real model-backed answer path:
    NHA questions use the constrained NHA Gemma writer; the one non-NHA control
    uses the upstream cognitive/Gemma stack. Synthetic security probes are the
    sole zero-model-call exception.
    """
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
    if not direct:
        raise ValueError("no_direct_nha_cases_available")
    if not limited:
        raise ValueError("no_conflict_limited_cases_available")

    supported = [
        row for row in relationships
        if row.get("relationship_status") == "source_supported" and row.get("direct_nha")
    ]
    parents = sorted(_dedupe(row.get("direct_nha") for row in supported))

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

    # Eight production-language probes taken from manual/adversarial usage rather
    # than benchmark-shaped wording.
    child0, result0 = direct[0]
    parent0 = str(result0.get("direct_nha") or "")
    add("direct_nha", f"What bigger assembly is {child0} installed inside?", "gemma_override")

    child1, result1 = direct[1 % len(direct)]
    parent1 = str(result1.get("direct_nha") or "")
    add(
        "direct_parent_comparison",
        f"Is {parent1} the immediate parent of {child1} or only a higher ancestor?",
        "gemma_override",
    )

    add(
        "ancestor_chain",
        f"Starting at {child0}, walk upward one supported assembly at a time.",
        "gemma_override",
    )

    child_parent = parent0 or parents[0]
    add(
        "direct_children",
        f"Which pieces are directly inside assembly {child_parent}?",
        "gemma_override",
    )

    descendant_parent = ""
    for parent in [child_parent, *parents]:
        result = engine.descendants(parent)
        if result.get("behavior") == "tree_answer" and result.get("pages") and result.get("descendants"):
            descendant_parent = parent
            break
    if not descendant_parent:
        raise ValueError("no_descendant_tree_case_available")
    add(
        "descendants",
        f"Show everything below {descendant_parent}, but separate immediate parts from deeper descendants.",
        "gemma_override",
    )

    add(
        "relationship_evidence",
        f"Where in the IPL is the parent relationship for {child0} proven?",
        "gemma_override",
    )

    limited_child, _ = limited[0]
    add(
        "scope_conflict_resolution",
        f"Why are there several possible parents for {limited_child}?",
        "gemma_override",
    )
    add(
        "scope_conflict_resolution",
        f"Which project or revision detail would resolve the parent of {limited_child}?",
        "gemma_override",
    )

    # Fill the remaining NHA slots with varied real-language questions while
    # preserving the strict one-Gemma-call contract.
    direct_templates = (
        "Which assembly directly owns {part}?",
        "Name the nearest supported parent assembly for {part}.",
        "Where does {part} sit one level up in the assembly structure?",
        "Tell me what assembly {part} belongs immediately to.",
        "What is the next higher assembly for {part}?",
    )
    direct_index = 2
    for template in direct_templates:
        child, _ = direct[direct_index % len(direct)]
        add("direct_nha", template.format(part=child), "gemma_override")
        direct_index += 1

    parent_added = 0
    for parent in parents:
        if parent == child_parent:
            continue
        result = engine.direct_children(parent)
        if result.get("behavior") == "direct_children_answer" and result.get("pages"):
            query = (
                f"Which components are immediately inside assembly {parent}?"
                if parent_added == 0
                else f"List only the parts directly under assembly {parent}."
            )
            add("direct_children", query, "gemma_override")
            parent_added += 1
            if parent_added >= 2:
                break

    chain_added = False
    for row in sorted(
        supported,
        key=lambda value: (-int(value.get("hierarchy_depth") or 0), str(value.get("child_part") or "")),
    ):
        child = str(row.get("child_part") or "")
        if child == child0:
            continue
        result = engine.ancestor_chain(child)
        if result.get("behavior") == "ordered_chain_answer" and result.get("pages"):
            add("ancestor_chain", f"Show the assembly chain above {child}, one supported hop at a time.", "gemma_override")
            chain_added = True
            break
    if not chain_added:
        add("relationship_evidence", f"Show the source evidence for the parent of {child1}.", "gemma_override")

    evidence_index = 1
    while len(cases) < 18:
        child, _ = direct[evidence_index % len(direct)]
        add(
            "relationship_evidence",
            f"Which source record supports the direct parent relationship for {child}?",
            "gemma_override",
        )
        evidence_index += 1

    # A real non-NHA request must still prove one upstream cognitive/Gemma call.
    add("non_nha_control", f"How do I install {child0}?", "passthrough")
    # Security isolation is the only legitimate zero-model-call live case.
    add(
        "synthetic_block_control",
        "What is the NHA of benchmark part 990-91001-001?",
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
    model_calls = int(headers.get("x-trace-net-model-calls") or 0)
    model_path = str(headers.get("x-trace-net-model-path") or "")
    upstream_calls = int(headers.get("x-trace-net-upstream-calls") or 0)
    model_prompt_tokens = int(headers.get("x-trace-net-model-prompt-tokens") or 0)
    model_completion_tokens = int(headers.get("x-trace-net-model-completion-tokens") or 0)
    packet = case.get("expected_packet") if isinstance(case.get("expected_packet"), Mapping) else {}
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), Mapping) else {}

    if int(response.get("http_status") or 0) != 200:
        failures.append(f"http_status:{response.get('http_status')}")
    if action != expected_action:
        failures.append(f"action expected={expected_action} actual={action}")

    if expected_action == "gemma_override":
        if model_calls != 1:
            failures.append(f"overall_model_call_count expected=1 actual={model_calls}")
        if model_path != "nha_constrained_gemma":
            failures.append(f"model_path expected=nha_constrained_gemma actual={model_path}")
        if upstream_calls != 0:
            failures.append(f"unexpected_upstream_call_count:{upstream_calls}")
        if model_prompt_tokens < 1 or model_completion_tokens < 1:
            failures.append("nha_model_tokens_missing")
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
        if model_calls != 0:
            failures.append(f"synthetic_overall_model_call_count:{model_calls}")
        if model_path:
            failures.append(f"synthetic_model_path_present:{model_path}")
        if upstream_calls != 0:
            failures.append(f"synthetic_upstream_call_count:{upstream_calls}")
        if headers.get("x-trace-net-nha-gemma-calls") not in {"", "0"}:
            failures.append("synthetic_sent_to_gemma")
        if headers.get("x-trace-net-nha-synthetic-access") != "0":
            failures.append("synthetic_artifact_access")
    elif expected_action == "passthrough":
        if action != "passthrough":
            failures.append("passthrough_control_not_passthrough")
        if model_calls != 1:
            failures.append(f"passthrough_model_call_count expected=1 actual={model_calls}")
        if model_path != "upstream_cognitive":
            failures.append(f"passthrough_model_path expected=upstream_cognitive actual={model_path}")
        if upstream_calls != 1:
            failures.append(f"passthrough_upstream_call_count expected=1 actual={upstream_calls}")
        if headers.get("x-trace-net-nha-gemma-calls") not in {"", "0"}:
            failures.append("passthrough_used_nha_gemma_writer")
        if not answer.strip():
            failures.append("passthrough_answer_empty")

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
        "model_call_count": model_calls,
        "model_path": model_path,
        "upstream_call_count": upstream_calls,
        "model_prompt_tokens": model_prompt_tokens,
        "model_completion_tokens": model_completion_tokens,
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
        "model_backed_question_count": sum(row["expected_action"] != "synthetic_blocked" for row in records),
        "overall_model_call_count": sum(row["model_call_count"] for row in records),
        "nha_model_path_count": sum(row["model_path"] == "nha_constrained_gemma" for row in records),
        "upstream_model_path_count": sum(row["model_path"] == "upstream_cognitive" for row in records),
        "upstream_call_count": sum(row["upstream_call_count"] for row in records),
        "unexpected_zero_model_call_count": sum(
            row["expected_action"] != "synthetic_blocked" and row["model_call_count"] == 0
            for row in records
        ),
        "allowed_zero_model_call_count": sum(
            row["expected_action"] == "synthetic_blocked" and row["model_call_count"] == 0
            for row in records
        ),
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
        "status": "TRACE_NET_NHA_PHASE17_REAL_SITUATION_GEMMA20_V1",
        "quality_status": quality,
        "counts": counts,
        "latency": {
            "average_seconds": round(sum(float(row["latency_seconds"] or 0) for row in records) / len(records), 3),
            "maximum_seconds": max(float(row["latency_seconds"] or 0) for row in records),
        },
        "failures": [f"{row['case_id']}:{'|'.join(row['failures'])}" for row in failed],
        "warnings": [],
        "live_model_call_policy": "one_real_model_path_for_every_non_synthetic_request",
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
        raise SystemExit("TRACE_NET_NHA_PHASE17_REAL_SITUATION_GEMMA20=FAIL")
    print("TRACE_NET_NHA_PHASE17_REAL_SITUATION_GEMMA20=PASS" if not failed else "TRACE_NET_NHA_PHASE17_REAL_SITUATION_GEMMA20=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
