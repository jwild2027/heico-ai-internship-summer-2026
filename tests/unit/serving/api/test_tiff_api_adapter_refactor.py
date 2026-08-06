from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from apps.api import tiff_api
from tiff.api_adapter_backend import (
    page_lookup_from_store,
    part_lookup_from_store,
    status_from_store,
    submit_feedback_from_store,
    trace_vector_payload_from_store,
)


class FakeCatalog:
    def organization_summary(self):
        return {"status": "ok", "pages": 1}

    def get_part(self, part_number: str):
        if part_number != "P-1":
            return None
        return {"part_number": "P-1", "nomenclature": "TEST PART", "pages": [{"page_id": "page-1"}]}

    def get_page(self, page_id: str):
        if page_id != "page-1":
            return None
        return {"page_id": "page-1", "source_url": "http://source/page-1", "summary": "context"}

    def get_ata(self, ata_code: str):
        return {"ata_code": ata_code, "pages": [{"page_id": "page-1"}]}


class FakeTrace:
    def trace_part(self, part_number: str, *, limit: int = 8):
        return {"status": "ok", "report": {"status": "OK", "summary": {"total_pages_found": 1}}}

    def trace_page(self, page_id: str, *, limit: int = 8):
        return {
            "status": "ok",
            "report": {
                "status": "OK",
                "summary": {"source_link_present": True, "context_present": True, "context_score": 0.9},
            },
        }

    def trace_vector_payload(self, page_id: str, *, chunk_id: str = "", score: float = 0.0):
        return {"status": "ok", "report": {"status": "OK", "summary": {"vector_payload_page_id": page_id}}}


class FakeAnswers:
    def ask(self, question: str, *, timeout_seconds: int = 120):
        return {"returncode": 0, "question": question, "answer_text": "answered", "llm_used": False, "embeddings_used": False}


class FakeFeedback:
    def __init__(self):
        self.records: list[Mapping[str, Any]] = []

    def submit_feedback(self, feedback: Mapping[str, Any]):
        self.records.append(feedback)
        return {"status": "ok", "count": len(self.records)}

    def feedback_summary(self):
        return {"status": "ok", "total": len(self.records)}


class FakeQuality:
    def status(self):
        return {
            "status": "ok",
            "quality": {"status": "OK"},
            "graph_quality": {"summary": {"nodes_total": 7, "page_context_nodes": 1, "source_link_nodes": 1}},
        }


class FakeSource:
    def resolve_page(self, page_id: str):
        return {"source_url": "http://source/page-1", "page_id": page_id}


@dataclass
class FakeBundle:
    catalog: Any = FakeCatalog()
    trace: Any = FakeTrace()
    answers: Any = FakeAnswers()
    feedback: Any = FakeFeedback()
    quality: Any = FakeQuality()
    keyword: Any = None
    vector: Any = None
    source: Any = FakeSource()
    mode: str = "fake"


def test_adapter_backend_part_page_status_and_vector_use_bundle():
    bundle = FakeBundle()
    status = status_from_store(bundle)
    assert status["status"] == "ok"
    assert status["graph"]["page_context_nodes"] == 1

    part = part_lookup_from_store("P-1", bundle=bundle)
    assert part["status"] == "ok"
    assert part["nomenclature"] == "TEST PART"
    assert part["pages_total"] == 1

    page = page_lookup_from_store("page-1", bundle=bundle)
    assert page["page"]["source_link_present"] is True
    assert page["page"]["context_present"] is True

    vector = trace_vector_payload_from_store(page_id="page-1", chunk_id="chunk-1", score=0.5, bundle=bundle)
    assert vector["status"] == "OK"


def test_feedback_uses_adapter_store():
    bundle = FakeBundle(feedback=FakeFeedback())
    result = submit_feedback_from_store(question="Q", rating="up", category="useful", reason="good", bundle=bundle)
    assert result["status"] == "ok"
    assert bundle.feedback.records[0]["question"] == "Q"


def test_fastapi_routes_call_store_bundle(monkeypatch):
    bundle = FakeBundle()
    monkeypatch.setattr(tiff_api, "get_store_bundle", lambda config_path="local_config.yaml": bundle)

    status = tiff_api.get_status()
    assert status["mode"] == "fake"

    part = tiff_api.get_part("P-1")
    assert part["status"] == "ok"

    page = tiff_api.get_page("page-1")
    assert page["page"]["context_present"] is True

    ask = tiff_api.post_ask(tiff_api.AskRequest(question="hello"))
    assert ask["answer_text"] == "answered"

    feedback = tiff_api.post_feedback(tiff_api.FeedbackRequest(question="hello", rating="up", answer="answered"))
    assert feedback["status"] == "ok"
