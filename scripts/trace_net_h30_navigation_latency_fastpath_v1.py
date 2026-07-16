#!/usr/bin/env python3
"""Exact-part navigation latency fastpath for TRACE-Net H30.

This overlay bounds only document/page navigation requests that contain a full
part number. It stops launching additional retrieval tunnels after an
entity-matching page has been found and caps the route's upstream calls.

It does not change retrieved records, evidence classification, critic rules,
answer rendering, source truth, or database state.
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


def _current_state() -> Optional[Dict[str, Any]]:
    value = getattr(_STATE, "value", None)
    return value if isinstance(value, dict) and value.get("active") else None


def _skip_reason(state: Mapping[str, Any], envelope: Any) -> str:
    if (
        int(state.get("used_calls") or 0) >= 1
        and _has_entity_page(envelope, set(state.get("requested_parts") or []))
    ):
        return "entity_matching_page_already_resolved"
    if int(state.get("used_calls") or 0) >= int(state.get("max_calls") or 2):
        return "navigation_upstream_budget_exhausted"
    return ""


def _skipped_result(label: str, reason: str) -> Dict[str, Any]:
    return {
        "quality_status": "SKIPPED",
        "route": "document_page_navigation",
        "skip_reason": reason,
        "tunnel": label,
        "read_only": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


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
            return _skipped_result(label, reason)

        state["used_calls"] += 1
        started = time.monotonic()
        status = 599
        try:
            result = invoke()
            status = int(result.get("status") or 200) if isinstance(result, Mapping) else 200
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
        active = bool(
            getattr(plan, "primary_route", "") == "document_page_navigation"
            and requested
        )

        state: Dict[str, Any] = {
            "active": active,
            "route": getattr(plan, "primary_route", ""),
            "requested_parts": sorted(requested),
            "max_calls": _max_calls(),
            "used_calls": 0,
            "skipped_tunnels": [],
            "tunnel_timings": [],
        }

        request_started = time.monotonic()
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
        summary = {
            "module": MODULE,
            "patch_id": PATCH_ID,
            "active": active,
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
            "read_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
        result["navigation_latency_fastpath"] = summary

        envelope = result.get("evidence_envelope")
        if isinstance(envelope, MutableMapping):
            coverage = envelope.get("coverage")
            if not isinstance(coverage, MutableMapping):
                coverage = {}
                envelope["coverage"] = coverage
            coverage["navigation_latency_fastpath"] = summary

        return result

    def health_v1(self: Any) -> Dict[str, Any]:
        result = dict(original_health(self))
        result.update({
            "navigation_latency_fastpath_v1": True,
            "navigation_max_upstream_calls": _max_calls(),
            "navigation_stops_after_entity_page": True,
            "navigation_other_routes_unchanged": True,
            "navigation_latency_metrics": True,
        })
        return result

    runtime_cls.add_unified = add_unified_v1
    runtime_cls.add_guided = add_guided_v1
    runtime_cls.process = process_v1
    runtime_cls.health = health_v1
    router["_H30_NAVIGATION_LATENCY_FASTPATH_V1_INSTALLED"] = True
