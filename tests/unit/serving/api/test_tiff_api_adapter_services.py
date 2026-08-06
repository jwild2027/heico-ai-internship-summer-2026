from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tiff.api_adapter_services import TiffApiServices
from tiff.storage_adapters import StoreBundle


class FakeCatalog:
    def organization_summary(self):
        return {"status": "ok", "summary": {"pages": 1}}

    def get_part(self, part_number: str, *, limit: int = 10):
        return {
            "status": "ok",
            "part_number": part_number,
            "nomenclature": "HOLDER, MAGAZINE",
            "pages_count": 1,
            "pages": [
                {
                    "page_id": "p1",
                    "page": {"page_id": "p1", "page_label": "1056", "manual_title": "Manual A", "ata_code": "25-21-00"},
                    "source": {"source_url": "http://source/p1"},
                    "context": {"summary": "A parts list page.", "confidence": "high"},
                }
            ],
        }

    def get_page(self, page_id: str):
        return {
            "status": "ok",
            "page": {"page_id": page_id, "page_label": "1056", "manual_title": "Manual A", "ata_code": "25-21-00"},
            "source": {"source_url": "http://source/p1"},
            "context": {"summary": "A parts list page.", "confidence": "high"},
            "parts": [{"part_number": "120-37313-001", "nomenclature": "HOLDER, MAGAZINE"}],
        }

    def get_ata(self, ata_code: str, *, limit: int = 20):
        return {
            "status": "ok",
            "ata_code": ata_code,
            "manual": "Manual A",
            "pages_count": 1,
            "pages": [{"page_id": "p1", "page": {"page_id": "p1"}, "source": {"source_url": "http://source/p1"}, "context": {"summary": "A parts list page."}}],
        }


class FakeVector:
    def trace_payload(self, *, page_id: str, chunk_id: str | None = None, score: float = 0.0):
        return {"status": "ok", "vector_payload": {"page_id": page_id, "chunk_id": chunk_id, "score": score}}


class FakeTrace:
    def trace_part(self, part_number: str, *, limit: int = 8):
        return {"status": "OK", "trace": "part", "part_number": part_number}

    def trace_page(self, page_id: str, *, limit: int = 8):
        return {"status": "OK", "trace": "page", "page_id": page_id}

    def trace_vector_payload(self, *, page_id: str, chunk_id: str | None = None, score: float = 0.0, limit: int = 8):
        return {"status": "OK", "trace": "vector", "page_id": page_id, "chunk_id": chunk_id, "score": score}


class FakeFeedback:
    def __init__(self):
        self.rows = []

    def save_feedback(self, feedback):
        self.rows.append(dict(feedback))
        return {"status": "ok", "summary": self.summary()}

    def summary(self):
        return {"status": "ok", "total": len(self.rows)}


class FakeQuality:
    def status(self):
        return {
            "status": "ok",
            "quality_gate": {"status": "OK", "summary": {"pipeline_status": "ok"}},
            "graph_quality": {"status": "OK", "summary": {"graph_present": True, "nodes_total": 7, "edges_total": 9, "page_nodes": 1, "page_context_nodes": 1, "source_link_nodes": 1, "pages_without_context": 0, "pages_without_source_links": 0}},
        }


class Unused:
    pass


def make_service() -> TiffApiServices:
    feedback = FakeFeedback()
    bundle = StoreBundle(
        catalog=FakeCatalog(),
        keyword_search=Unused(),
        vector=FakeVector(),
        source=Unused(),
        feedback=feedback,
        quality=FakeQuality(),
        trace=FakeTrace(),
    )
    return TiffApiServices(stores=bundle, repo_root=Path("."))


def test_adapter_service_normalizes_part_page_and_status():
    service = make_service()
    status = service.api_status()
    assert status["status"] == "OK"
    assert status["graph"]["page_context_nodes"] == 1

    part = service.part_lookup("120-37313-001")
    assert part["status"] == "ok"
    assert part["nomenclature"] == "HOLDER, MAGAZINE"
    assert part["pages"][0]["source_link_present"] is True
    assert part["pages"][0]["context_present"] is True

    page = service.page_lookup("p1")
    assert page["status"] == "ok"
    assert page["page"]["document"] == "Manual A"
    assert page["parts"][0]["nomenclature"] == "HOLDER, MAGAZINE"


def test_adapter_service_uses_trace_and_feedback_adapters():
    service = make_service()
    assert service.trace_part("120-37313-001")["trace"] == "part"
    assert service.trace_page("p1")["trace"] == "page"
    vector = service.trace_vector_payload("p1", chunk_id="chunk1", score=0.42)
    assert vector["trace"] == "vector"
    assert vector["chunk_id"] == "chunk1"

    saved = service.submit_feedback(question="q", rating="up", category="useful", reason="good")
    assert saved["status"] == "ok"
    assert service.summarize_feedback()["total"] == 1
