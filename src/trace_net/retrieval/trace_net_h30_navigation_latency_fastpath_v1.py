#!/usr/bin/env python3
"""Exact-part navigation latency fastpath and general retrieval budget for TRACE-Net H30.

This overlay bounds retrieval latency in two complementary ways, both using the
same thread-local per-request budget state and the same add_unified/add_guided
chokepoint:

1. Navigation fastpath (always active for document/page navigation requests that
   contain a full part number): stops launching additional retrieval tunnels
   after an entity-matching page has been found and caps that route's upstream
   calls.

2. General retrieval budget (env-gated via TRACE_NET_H30_RETRIEVAL_BUDGET_ENABLED,
   applies to every route): enforces an overall wall-clock retrieval deadline, a
   per-tunnel upstream timeout, a maximum number of executed tunnels, and a
   per-tunnel candidate cap. This is the bound that prevents an unbounded serial
   fan-out of upstream calls (each otherwise limited only by the 1200s socket
   timeout) from summing to hundreds of seconds on a single question.

It does not change retrieved records, evidence classification, critic rules,
answer rendering, source truth, or database state. Skipping a tunnel only
prevents an additional upstream call; it never fabricates evidence.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any, Dict, Mapping, MutableMapping, Optional

MODULE = "trace_net_h30_navigation_latency_fastpath_v1"
PATCH_ID = "trace_net_h30_phase4_2_0_1_navigation_latency_fastpath_v1"
PART_RE = re.compile(r"\b\d{2,3}-\d{5}-\d{3}\b", re.I)
_STATE = threading.local()


def _compact(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _requested_parts(atoms: Any) -> set[str]:
    return {
        str(value).upper()
        for value in (getattr(atoms, "exact_part_numbers", None) or [])
        if PART_RE.fullmatch(str(value).strip())
    }


def _row_has_requested_page(row: Mapping[str, Any], requested: set[str]) -> bool:
    page = _compact(
        row.get("page_id")
        or row.get("source_page_id")
        or row.get("document_page_id"),
        300,
    )
    if not page:
        return False
    blob = _compact(row, 12000).upper()
    return any(part in blob for part in requested)


def _has_entity_page(envelope: Any, requested: set[str]) -> bool:
    if not requested:
        return False

    for attribute in (
        "direct_evidence",
        "visual_guidance",
        "candidate_evidence",
    ):
        for row in getattr(envelope, attribute, None) or []:
            if isinstance(row, Mapping) and _row_has_requested_page(row, requested):
                return True

    coverage = getattr(envelope, "coverage", None)
    if isinstance(coverage, Mapping):
        for row in coverage.get("navigation_leads", []) or []:
            if isinstance(row, Mapping) and _row_has_requested_page(row, requested):
                return True
    return False


def _max_calls() -> int:
    raw = os.environ.get("TRACE_NET_NAVIGATION_MAX_UPSTREAM_CALLS", "2")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 2
    return max(1, min(value, 5))


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _budget_float(name: str, default: float, low: float, high: float) -> float:
    raw = os.environ.get(name)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    return max(low, min(value, high))


def _budget_int(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(low, min(value, high))


def _budget_enabled() -> bool:
    # Off at the module level so unit tests and direct process invocation keep
    # legacy behavior; the deployment launcher opts in with =1.
    return _bool_env("TRACE_NET_H30_RETRIEVAL_BUDGET_ENABLED", False)


def _retrieval_deadline_seconds() -> float:
    return _budget_float("TRACE_NET_H30_RETRIEVAL_DEADLINE_SECONDS", 120.0, 5.0, 1200.0)


def _retrieval_per_tunnel_timeout() -> float:
    return _budget_float("TRACE_NET_H30_RETRIEVAL_PER_TUNNEL_TIMEOUT_SECONDS", 45.0, 1.0, 1200.0)


def _retrieval_max_tunnels() -> int:
    return _budget_int("TRACE_NET_H30_RETRIEVAL_MAX_TUNNELS", 16, 1, 64)


def _retrieval_max_candidates_per_tunnel() -> int:
    return _budget_int("TRACE_NET_H30_RETRIEVAL_MAX_CANDIDATES_PER_TUNNEL", 10, 1, 100)


def _current_state() -> Optional[Dict[str, Any]]:
    value = getattr(_STATE, "value", None)
    return value if isinstance(value, dict) and value.get("active") else None


def _skip_reason(state: Mapping[str, Any], envelope: Any) -> str:
    used = int(state.get("used_calls") or 0)

    # Navigation-specific early stop: only for the exact-part navigation fastpath.
    if state.get("nav_active"):
        if used >= 1 and _has_entity_page(
            envelope, set(state.get("requested_parts") or [])
        ):
            return "entity_matching_page_already_resolved"
        if used >= int(state.get("max_calls") or 2):
            return "navigation_upstream_budget_exhausted"

    # General retrieval budget: applies to every route when enabled. Both the
    # overall wall-clock deadline and the max-tunnels count are hard bounds; the
    # deadline is checked before each call so worst-case latency is the deadline
    # plus at most one per-tunnel timeout.
    if state.get("budget_enabled"):
        deadline = state.get("deadline")
        if deadline is not None and time.monotonic() >= float(deadline):
            return "retrieval_deadline_exhausted"
        if used >= int(state.get("global_max_calls") or 16):
            return "retrieval_max_tunnels_exhausted"
    return ""


def _skipped_result(
    label: str,
    reason: str,
    route: str = "document_page_navigation",
) -> Dict[str, Any]:
    return {
        "quality_status": "SKIPPED",
        "route": route,
        "skip_reason": reason,
        "tunnel": label,
        "read_only": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def _numeric_status(value: Any, default: int = 200) -> int:
    """Coerce a transport status_code to an int. Upstream *payloads* use
    semantic string statuses (e.g. TRACE_NET_..._DONE), so only genuine numeric
    values are accepted; anything else falls back to the default."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return default


def install_navigation_latency_fastpath(router: MutableMapping[str, Any]) -> None:
    """Install after retrieval completion, critic repair, and user-facing rendering."""
    if router.get("_H30_NAVIGATION_LATENCY_FASTPATH_V1_INSTALLED"):
        return

    runtime_cls = router["CognitiveRuntime"]
    original_add_unified = runtime_cls.add_unified
    original_add_guided = runtime_cls.add_guided
    original_process = runtime_cls.process
    original_health = runtime_cls.health
    extract_latest_user = router["extract_latest_user"]
    extract_query_atoms = router["extract_query_atoms"]
    plan_route = router["plan_route"]

    def call_with_budget(
        self: Any,
        *,
        kind: str,
        envelope: Any,
        query: str,
        label: str,
        invoke: Any,
    ) -> Dict[str, Any]:
        state = _current_state()
        if state is None:
            return invoke()

        reason = _skip_reason(state, envelope)
        if reason:
            state["skipped_tunnels"].append({
                "kind": kind,
                "tunnel": label,
                "reason": reason,
            })
            return _skipped_result(
                label,
                reason,
                str(state.get("route") or "document_page_navigation"),
            )

        state["used_calls"] += 1
        started = time.monotonic()
        status = 200
        try:
            result = invoke()
            # The HTTP status was already recorded by add_unified/add_guided in
            # envelope.upstream_results[].status_code. Read it from there. Never
            # int() result["status"]: upstream payloads carry a SEMANTIC string
            # status such as TRACE_NET_GUIDED_CANDIDATE_DISCOVERY_ENDPOINT_V1_DONE.
            for row in reversed(getattr(envelope, "upstream_results", None) or []):
                if not isinstance(row, Mapping):
                    continue
                if str(row.get("tunnel") or "") != label:
                    continue
                status = _numeric_status(row.get("status_code"), 200)
                break
            else:
                if isinstance(result, Mapping):
                    status = _numeric_status(result.get("status_code"), 200)
            return result
        finally:
            elapsed_ms = (time.monotonic() - started) * 1000.0
            state["tunnel_timings"].append({
                "kind": kind,
                "tunnel": label,
                "elapsed_ms": round(elapsed_ms, 3),
                "status_code": status,
                "entity_page_after_call": _has_entity_page(
                    envelope,
                    set(state.get("requested_parts") or []),
                ),
            })

    def add_unified_v1(self: Any, envelope: Any, query: str, label: str) -> Dict[str, Any]:
        return call_with_budget(
            self,
            kind="unified",
            envelope=envelope,
            query=query,
            label=label,
            invoke=lambda: original_add_unified(self, envelope, query, label),
        )

    def add_guided_v1(
        self: Any,
        envelope: Any,
        query: str,
        atoms: Any,
        label: str,
        *,
        allow_broad: bool = False,
    ) -> Dict[str, Any]:
        return call_with_budget(
            self,
            kind="guided",
            envelope=envelope,
            query=query,
            label=label,
            invoke=lambda: original_add_guided(
                self,
                envelope,
                query,
                atoms,
                label,
                allow_broad=allow_broad,
            ),
        )

    def process_v1(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        query = extract_latest_user(payload)
        atoms = extract_query_atoms(query)
        plan = plan_route(atoms)
        requested = _requested_parts(atoms)
        nav_active = bool(
            getattr(plan, "primary_route", "") == "document_page_navigation"
            and requested
        )
        budget_enabled = _budget_enabled()
        active = bool(nav_active or budget_enabled)

        deadline_seconds = _retrieval_deadline_seconds()
        per_tunnel_timeout = _retrieval_per_tunnel_timeout()
        global_max_calls = _retrieval_max_tunnels()
        max_candidates = _retrieval_max_candidates_per_tunnel()

        request_started = time.monotonic()
        state: Dict[str, Any] = {
            "active": active,
            "nav_active": nav_active,
            "budget_enabled": budget_enabled,
            "route": getattr(plan, "primary_route", ""),
            "requested_parts": sorted(requested),
            "max_calls": _max_calls(),
            "global_max_calls": global_max_calls,
            "deadline": (request_started + deadline_seconds) if budget_enabled else None,
            "deadline_seconds": deadline_seconds,
            "per_tunnel_timeout": per_tunnel_timeout,
            "max_candidates_per_tunnel": max_candidates,
            "used_calls": 0,
            "skipped_tunnels": [],
            "tunnel_timings": [],
        }

        # Bound each upstream call and per-tunnel candidate volume when the
        # general budget is enabled. These are static config values (identical
        # across concurrent requests), so setting them on the shared runtime
        # instance is safe; the base call_unified/call_guided/add_guided read
        # them via getattr and fall back to legacy behavior when unset.
        if budget_enabled:
            self.retrieval_timeout = per_tunnel_timeout
            self.max_candidates_per_tunnel = max_candidates

        previous = getattr(_STATE, "value", None)
        _STATE.value = state
        try:
            result = dict(original_process(self, payload))
        finally:
            _STATE.value = previous

        total_ms = (time.monotonic() - request_started) * 1000.0
        upstream_ms = sum(
            float(row.get("elapsed_ms") or 0)
            for row in state["tunnel_timings"]
        )
        skip_reasons = [str(row.get("reason") or "") for row in state["skipped_tunnels"]]
        summary = {
            "module": MODULE,
            "patch_id": PATCH_ID,
            "active": active,
            "nav_active": nav_active,
            "route": state["route"],
            "requested_parts": state["requested_parts"],
            "max_upstream_calls": state["max_calls"],
            "used_upstream_calls": state["used_calls"],
            "skipped_upstream_calls": len(state["skipped_tunnels"]),
            "skipped_tunnels": list(state["skipped_tunnels"]),
            "tunnel_timings": list(state["tunnel_timings"]),
            "upstream_total_ms": round(upstream_ms, 3),
            "request_total_ms": round(total_ms, 3),
            "non_upstream_ms": round(max(0.0, total_ms - upstream_ms), 3),
            "stops_after_entity_page": True,
            "budget_enabled": budget_enabled,
            "retrieval_deadline_seconds": deadline_seconds if budget_enabled else None,
            "retrieval_per_tunnel_timeout_seconds": per_tunnel_timeout if budget_enabled else None,
            "retrieval_max_tunnels": global_max_calls if budget_enabled else None,
            "retrieval_max_candidates_per_tunnel": max_candidates if budget_enabled else None,
            "retrieval_deadline_exhausted": "retrieval_deadline_exhausted" in skip_reasons,
            "retrieval_max_tunnels_exhausted": "retrieval_max_tunnels_exhausted" in skip_reasons,
            "read_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
        result["navigation_latency_fastpath"] = summary
        result["retrieval_budget"] = summary

        envelope = result.get("evidence_envelope")
        if isinstance(envelope, MutableMapping):
            coverage = envelope.get("coverage")
            if not isinstance(coverage, MutableMapping):
                coverage = {}
                envelope["coverage"] = coverage
            coverage["navigation_latency_fastpath"] = summary
            coverage["retrieval_budget"] = summary

        return result

    def health_v1(self: Any) -> Dict[str, Any]:
        result = dict(original_health(self))
        result.update({
            "navigation_latency_fastpath_v1": True,
            "navigation_max_upstream_calls": _max_calls(),
            "navigation_stops_after_entity_page": True,
            "navigation_other_routes_unchanged": True,
            "navigation_latency_metrics": True,
            "retrieval_budget_enabled": _budget_enabled(),
            "retrieval_budget_all_routes": True,
            "retrieval_deadline_seconds": _retrieval_deadline_seconds(),
            "retrieval_per_tunnel_timeout_seconds": _retrieval_per_tunnel_timeout(),
            "retrieval_max_tunnels": _retrieval_max_tunnels(),
            "retrieval_max_candidates_per_tunnel": _retrieval_max_candidates_per_tunnel(),
        })
        return result

    runtime_cls.add_unified = add_unified_v1
    runtime_cls.add_guided = add_guided_v1
    runtime_cls.process = process_v1
    runtime_cls.health = health_v1
    router["_H30_NAVIGATION_LATENCY_FASTPATH_V1_INSTALLED"] = True
