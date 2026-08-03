#!/usr/bin/env python3
"""Strong end-to-end check for TRACE-Net truthful OpenWebUI stack v2."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


def request(url: str, *, api_key: Optional[str], payload: Optional[Mapping[str, Any]] = None, timeout: float = 240.0) -> Tuple[int, Dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="GET" if payload is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            value = json.loads(resp.read().decode("utf-8"))
            return resp.status, value if isinstance(value, dict) else {}
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read().decode("utf-8"))
        except Exception:
            value = {}
        return exc.code, value


def trace_from_openai(response: Mapping[str, Any]) -> Dict[str, Any]:
    value = response.get("trace_net")
    return dict(value) if isinstance(value, Mapping) else {}


def run(args: argparse.Namespace) -> Dict[str, Any]:
    base = args.base_url.rstrip("/")
    records = []

    status, health = request(base.removesuffix("/v1") + "/health", api_key=None, timeout=args.timeout)
    health_failures = []
    if status != 200 or health.get("quality_status") != "PASS":
        health_failures.append("front_door_health_not_pass")
    if not (health.get("qdrant") or {}).get("connected"):
        health_failures.append("qdrant_not_connected")
    if not health.get("graph_guidance_connected"):
        health_failures.append("graph_guidance_not_connected")
    if not health.get("v2_summary_guidance_connected"):
        health_failures.append("v2_summary_not_connected")
    if int((health.get("engram") or {}).get("record_count") or 0) <= 0:
        health_failures.append("engram_not_loaded")

    status, models = request(base + "/models", api_key=args.api_key, timeout=args.timeout)
    model_ids = [m.get("id") for m in models.get("data", []) if isinstance(m, dict)]
    models_ok = status == 200 and args.model in model_ids

    unauth_status, _ = request(base + "/models", api_key="wrong-key", timeout=args.timeout)
    unauthorized_ok = unauth_status == 401

    cases = [
        ("visual_general", [{"role":"user","content":"Show figure references for passenger seat assembly diagram"}], "gemma_confirmed_image_visual"),
        ("visual_exact", [{"role":"user","content":"Find diagram for part number 120-41824-003"}], "gemma_confirmed_image_visual"),
        ("normal_exact", [{"role":"user","content":"Find part number 120-41824-003"}], "normal_ask"),
        ("guided_partial", [{"role":"user","content":"I only know the part starts with 24"}], "guided_discovery"),
        ("multiturn_visual", [
            {"role":"user","content":"Find part number 120-41824-003"},
            {"role":"assistant","content":"Okay."},
            {"role":"user","content":"What figure is it in?"},
        ], "gemma_confirmed_image_visual"),
    ]

    for name, messages, expected_route in cases:
        status, response = request(
            base + "/chat/completions",
            api_key=args.api_key,
            payload={"model": args.model, "messages": messages, "temperature": 0},
            timeout=args.timeout,
        )
        trace = trace_from_openai(response)
        failures = []
        if status != 200:
            failures.append(f"http_status:{status}")
        if trace.get("route") != expected_route:
            failures.append(f"route:{trace.get('route')}")
        content = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        if not isinstance(content, str) or not content.strip() or content.lstrip().startswith("{"):
            failures.append("visible_answer_not_human_readable")
        if trace.get("self_rag_critic", {}).get("quality_status") not in {"PASS", "RETRY"}:
            failures.append("self_rag_missing")
        if trace.get("answer_permission") or trace.get("final_answer_allowed") or trace.get("source_truth_mutation_allowed"):
            failures.append("safety_true")

        if name == "visual_exact":
            citations = trace.get("citations") or []
            if not citations:
                failures.append("no_visual_exact_citations")
            for c in citations:
                if "120-41824-003" not in (c.get("part_numbers") or []):
                    failures.append("unrelated_visual_exact_citation")
                    break
        elif name == "normal_exact":
            if int(trace.get("downstream_status_code") or 0) != 200:
                failures.append("normal_downstream_not_200")
            if trace.get("final_gate_status") not in {"LIVE_ORCHESTRATOR_FINAL_GATE_PASS", "LIVE_ORCHESTRATOR_AUDIT_ONLY"}:
                failures.append("normal_final_gate_missing")
            if trace.get("final_answer_ready_for_webui") and int(trace.get("citation_count") or 0) <= 0:
                failures.append("normal_ready_without_citations")
        elif name == "guided_partial":
            downstream = trace.get("downstream_response") or {}
            if int(trace.get("downstream_status_code") or 0) != 200:
                failures.append("guided_downstream_not_200")
            if downstream.get("quality_status") != "PASS":
                failures.append("guided_downstream_not_pass")
            if not (downstream.get("candidate_routes") or downstream.get("clarifying_questions")):
                failures.append("guided_empty")
        elif name == "multiturn_visual":
            if not trace.get("working_memory_applied"):
                failures.append("working_memory_not_applied")

        records.append({
            "name": name,
            "expected_route": expected_route,
            "route": trace.get("route"),
            "quality_status": "PASS" if not failures else "FAIL",
            "failures": failures,
            "citation_count": trace.get("citation_count"),
            "working_memory_applied": trace.get("working_memory_applied"),
        })
        print(f"{name}: route={trace.get('route')} expected={expected_route} status={records[-1]['quality_status']}")
        if failures:
            print("  failures=" + json.dumps(failures))

    fail_count = sum(1 for r in records if r["quality_status"] != "PASS")
    if health_failures:
        fail_count += 1
    if not models_ok:
        fail_count += 1
    if not unauthorized_ok:
        fail_count += 1
    return {
        "status": "TRACE_NET_OPENWEBUI_TRUTHFUL_LIVE_STACK_V2_CHECK_DONE",
        "quality_status": "PASS" if fail_count == 0 else "FAIL",
        "health_failures": health_failures,
        "models_ok": models_ok,
        "unauthorized_request_rejected": unauthorized_ok,
        "record_count": len(records),
        "record_fail_count": sum(1 for r in records if r["quality_status"] != "PASS"),
        "total_fail_count": fail_count,
        "records": records,
        "health": health,
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:8017/v1")
    p.add_argument("--api-key", default="trace-net-local")
    p.add_argument("--model", default="trace-net-openwebui-unified-rag-v2")
    p.add_argument("--timeout", type=float, default=240.0)
    p.add_argument("--output-dir", default="local_data/organization/trace_net/openwebui_truthful_live_stack_v2_check")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    result = run(args)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for key in ("status","quality_status","models_ok","unauthorized_request_rejected","record_count","record_fail_count","total_fail_count"):
        print(f"{key}={result[key]}")
    return 0 if result["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
