from __future__ import annotations

from dataclasses import dataclass, field

from src.trace_net.router.trace_net_h30_phase19_route_completion_fastpath_v1 import (
    evidence_sufficient,
    install_phase19_route_completion_fastpath,
)


@dataclass
class Envelope:
    direct_evidence: list = field(default_factory=list)
    candidate_evidence: list = field(default_factory=list)
    visual_guidance: list = field(default_factory=list)
    semantic_guidance: list = field(default_factory=list)
    authority_evidence: list = field(default_factory=list)
    upstream_results: list = field(default_factory=list)


@dataclass
class Atoms:
    latest_query: str
    exact_part_numbers: list = field(default_factory=list)
    ata_exact: list = field(default_factory=list)
    ata_prefix: str | None = None


@dataclass
class Plan:
    primary_route: str


class BaseRuntime:
    def __init__(self):
        self.actual_calls = []

    def add_unified(self, envelope, query, label):
        self.actual_calls.append(label)
        if "ATA" in query:
            envelope.direct_evidence.append({
                "page_id": "t_p_120_1176_p000071",
                "value": "ATA 25-21-00 source section",
            })
        else:
            envelope.direct_evidence.append({
                "page_id": "t_p_120_1176_p000343",
                "normalized_value": "120-20970-001",
            })
        return {"quality_status": "PASS"}

    def add_guided(self, envelope, query, atoms, label, *, allow_broad=False):
        self.actual_calls.append(label)
        return {"quality_status": "PASS"}

    def process(self, payload):
        envelope = Envelope()
        self.add_unified(envelope, payload["query"], "first")
        self.add_guided(envelope, payload["query"], None, "second")
        self.add_unified(envelope, payload["query"], "third")
        return {
            "content": "ok",
            "evidence_envelope": {"coverage": {}},
        }

    def health(self):
        return {"quality_status": "PASS"}


def _router(route):
    class Runtime(BaseRuntime):
        pass

    def atoms(query):
        if route == "ata_system_discovery":
            return Atoms(query, ata_exact=["25-21-00"])
        return Atoms(query, exact_part_numbers=["120-20970-001"])

    return {
        "CognitiveRuntime": Runtime,
        "extract_latest_user": lambda payload: payload["query"],
        "extract_query_atoms": atoms,
        "plan_route": lambda value: Plan(route),
    }


def test_exact_part_stops_after_matching_source_page(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_ENABLED", "1")
    router = _router("exact_identifier_lookup")
    install_phase19_route_completion_fastpath(router)
    runtime = router["CognitiveRuntime"]()
    result = runtime.process({"query": "Find part 120-20970-001."})
    summary = result["phase19_route_completion_fastpath"]
    assert runtime.actual_calls == ["first"]
    assert summary["active"] is True
    assert summary["executed_calls"] == 1
    assert summary["skipped_call_count"] == 2
    assert summary["matching_source_page_resolved"] is True


def test_ata_stops_after_matching_source_page(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_ENABLED", "1")
    router = _router("ata_system_discovery")
    install_phase19_route_completion_fastpath(router)
    runtime = router["CognitiveRuntime"]()
    result = runtime.process({"query": "Find ATA 25-21-00."})
    summary = result["phase19_route_completion_fastpath"]
    assert runtime.actual_calls == ["first"]
    assert summary["executed_calls"] == 1
    assert summary["matching_source_page_resolved"] is True


def test_disabled_overlay_does_not_skip(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PHASE19_ROUTE_COMPLETION_ENABLED", "0")
    router = _router("exact_identifier_lookup")
    install_phase19_route_completion_fastpath(router)
    runtime = router["CognitiveRuntime"]()
    result = runtime.process({"query": "Find part 120-20970-001."})
    assert runtime.actual_calls == ["first", "second", "third"]
    assert result["phase19_route_completion_fastpath"]["active"] is False


def test_evidence_requires_page_and_requested_token():
    envelope = Envelope(direct_evidence=[{
        "page_id": "t_p_120_1176_p000343",
        "value": "120-20970-001",
    }])
    assert evidence_sufficient("exact_identifier_lookup", envelope, ["120-20970-001"], [])
    assert not evidence_sufficient("exact_identifier_lookup", envelope, ["120-20970-003"], [])
