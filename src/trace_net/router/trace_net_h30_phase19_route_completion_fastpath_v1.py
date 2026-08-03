#!/usr/bin/env python3
"""Route-completion early stop for exact part, IPL, and ATA cognitive retrieval.

This overlay never fabricates evidence. It only stops launching additional
retrieval tunnels after the current request already has a matching source page,
or after a small route-specific call budget is exhausted. Existing critic,
CRAG, source authority, rendering, and safety validation remain authoritative.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any, Dict, Iterable, Mapping, MutableMapping

MODULE = "trace_net_h30_phase19_route_completion_fastpath_v1"
STATUS = "TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_FASTPATH_V1"
PATCH_ID = "trace_net_h30_phase19_route_completion_fastpath_v1"
PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b", re.I)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
SUPPORTED_ROUTES = {
    "exact_identifier_lookup",
    "exact_table_ipl_lookup",
    "ata_system_discovery",
}
_STATE = threading.local()


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, low: int = 1, high: int = 8) -> int:
    try:
        value = int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def enabled() -> bool:
    return _bool_env("TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_ENABLED", False)


def route_max_calls(route: str) -> int:
    names = {
        "exact_identifier_lookup": "TRACE_NET_H30_PHASE19_EXACT_IDENTIFIER_MAX_CALLS",
        "exact_table_ipl_lookup": "TRACE_NET_H30_PHASE19_EXACT_TABLE_MAX_CALLS",
        "ata_system_discovery": "TRACE_NET_H30_PHASE19_ATA_MAX_CALLS",
    }
    defaults = {
        "exact_identifier_lookup": 2,
        "exact_table_ipl_lookup": 2,
        "ata_system_discovery": 2,
    }
    return _int_env(names.get(route, "TRACE_NET_H30_PHASE19_ROUTE_MAX_CALLS"), defaults.get(route, 2))


def _compact(value: Any, limit: int = 16000) -> str:
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


def _requested_parts(atoms: Any) -> list[str]:
    return [
        str(value).upper()
        for value in (getattr(atoms, "exact_part_numbers", None) or [])
        if PART_RE.fullmatch(str(value).strip())
    ]


def _requested_atas(atoms: Any) -> list[str]:
    values = list(getattr(atoms, "ata_exact", None) or [])
    prefix = getattr(atoms, "ata_prefix", None)
    if prefix:
        values.append(prefix)
    return [str(value).upper() for value in values if ATA_RE.fullmatch(str(value).strip())]


def _iter_evidence_rows(envelope: Any) -> Iterable[Mapping[str, Any]]:
    for attribute in (
        "direct_evidence",
        "candidate_evidence",
        "visual_guidance",
        "semantic_guidance",
        "authority_evidence",
        "upstream_results",
    ):
        for row in getattr(envelope, attribute, None) or []:
            if isinstance(row, Mapping):
                yield row


def _row_has_page_and_token(row: Mapping[str, Any], tokens: Iterable[str]) -> bool:
    blob = _compact(row).upper()
    if not PAGE_RE.search(blob):
        return False
    return any(token and token.upper() in blob for token in tokens)


def evidence_sufficient(route: str, envelope: Any, parts: Iterable[str], atas: Iterable[str]) -> bool:
    tokens = list(atas if route == "ata_system_discovery" else parts)
    if not tokens:
        return False
    return any(_row_has_page_and_token(row, tokens) for row in _iter_evidence_rows(envelope))


def _state() -> Dict[str, Any] | None:
    value = getattr(_STATE, "value", None)
    return value if isinstance(value, dict) and value.get("active") else None


def _skip_reason(state: Mapping[str, Any], envelope: Any) -> str:
    used = int(state.get("executed_calls") or 0)
    sufficient = evidence_sufficient(
        str(state.get("route") or ""),
        envelope,
        state.get("requested_parts") or [],
        state.get("requested_atas") or [],
    )
    if used >= 1 and sufficient:
        return "matching_source_page_already_resolved"
    if used >= int(state.get("max_calls") or 2):
        return "route_call_budget_exhausted"
    return ""


def _skipped_result(route: str, label: str, reason: str) -> Dict[str, Any]:
    return {
        "quality_status": "SKIPPED",
        "route": route,
        "tunnel": label,
        "skip_reason": reason,
        "read_only": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def install_phase19_route_completion_fastpath(router: MutableMapping[str, Any]) -> None:
    marker = "_TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_FASTPATH_V1_INSTALLED"
    if router.get(marker):
        return

    runtime_cls = router["CognitiveRuntime"]
    current_add_unified = runtime_cls.add_unified
    current_add_guided = runtime_cls.add_guided
    current_process = runtime_cls.process
    current_health = runtime_cls.health
    extract_latest_user = router["extract_latest_user"]
    extract_query_atoms = router["extract_query_atoms"]
    plan_route = router["plan_route"]

    def _invoke(
        self: Any,
        *,
        envelope: Any,
        label: str,
        kind: str,
        call: Any,
    ) -> Dict[str, Any]:
        state = _state()
        if state is None:
            return call()
        reason = _skip_reason(state, envelope)
        if reason:
            state["skipped_calls"].append({"kind": kind, "tunnel": label, "reason": reason})
            return _skipped_result(str(state.get("route") or ""), label, reason)

        state["executed_calls"] += 1
        started = time.monotonic()
        result = call()
        state["call_timings"].append({
            "kind": kind,
            "tunnel": label,
            "elapsed_ms": round((time.monotonic() - started) * 1000.0, 3),
            "matching_source_page_after_call": evidence_sufficient(
                str(state.get("route") or ""),
                envelope,
                state.get("requested_parts") or [],
                state.get("requested_atas") or [],
            ),
        })
        return result

    def add_unified_v1(self: Any, envelope: Any, query: str, label: str) -> Dict[str, Any]:
        return _invoke(
            self,
            envelope=envelope,
            label=label,
            kind="unified",
            call=lambda: current_add_unified(self, envelope, query, label),
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
        return _invoke(
            self,
            envelope=envelope,
            label=label,
            kind="guided",
            call=lambda: current_add_guided(
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
        route = str(getattr(plan, "primary_route", "") or "")
        active = bool(enabled() and route in SUPPORTED_ROUTES)
        state: Dict[str, Any] = {
            "active": active,
            "route": route,
            "requested_parts": _requested_parts(atoms),
            "requested_atas": _requested_atas(atoms),
            "max_calls": route_max_calls(route),
            "executed_calls": 0,
            "skipped_calls": [],
            "call_timings": [],
        }
        previous = getattr(_STATE, "value", None)
        _STATE.value = state
        started = time.monotonic()
        try:
            result = dict(current_process(self, payload))
        finally:
            _STATE.value = previous

        summary = {
            "status": STATUS,
            "module": MODULE,
            "patch_id": PATCH_ID,
            "enabled": enabled(),
            "active": active,
            "route": route,
            "requested_parts": list(state["requested_parts"]),
            "requested_atas": list(state["requested_atas"]),
            "max_calls": state["max_calls"],
            "executed_calls": state["executed_calls"],
            "skipped_call_count": len(state["skipped_calls"]),
            "skipped_calls": list(state["skipped_calls"]),
            "call_timings": list(state["call_timings"]),
            "request_total_ms": round((time.monotonic() - started) * 1000.0, 3),
            "matching_source_page_resolved": any(
                bool(row.get("matching_source_page_after_call"))
                for row in state["call_timings"]
            ),
            "read_only": True,
            "retrieval_fanout_changed": active,
            "retrieval_result_mutation": False,
            "ranking_changed": False,
            "source_truth_mutation_allowed": False,
        }
        result["phase19_route_completion_fastpath"] = summary
        envelope = result.get("evidence_envelope")
        if isinstance(envelope, MutableMapping):
            coverage = envelope.get("coverage")
            if not isinstance(coverage, MutableMapping):
                coverage = {}
                envelope["coverage"] = coverage
            coverage["phase19_route_completion_fastpath"] = summary
        return result

    def health_v1(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        result["phase19_route_completion_fastpath"] = {
            "status": STATUS,
            "enabled": enabled(),
            "routes": sorted(SUPPORTED_ROUTES),
            "exact_identifier_max_calls": route_max_calls("exact_identifier_lookup"),
            "exact_table_max_calls": route_max_calls("exact_table_ipl_lookup"),
            "ata_max_calls": route_max_calls("ata_system_discovery"),
            "stops_after_matching_source_page": True,
            "read_only": True,
            "source_truth_mutation_allowed": False,
        }
        return result

    runtime_cls.add_unified = add_unified_v1
    runtime_cls.add_guided = add_guided_v1
    runtime_cls.process = process_v1
    runtime_cls.health = health_v1
    router[marker] = True


__all__ = [
    "MODULE",
    "STATUS",
    "PATCH_ID",
    "SUPPORTED_ROUTES",
    "enabled",
    "route_max_calls",
    "evidence_sufficient",
    "install_phase19_route_completion_fastpath",
]
