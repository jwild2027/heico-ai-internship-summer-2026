from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HELPER = Path("src/trace_net/pipeline/s6_retrieval/search/trace_net_h30_retrieval_completion_v1.py")
BOUNDARY = Path("src/trace_net/validation/trace_net_h30_answer_boundary_v1.py")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def make_artifacts(root: Path) -> None:
    (root / "ocr_records").mkdir(parents=True)
    (root / "visual_evidence").mkdir(parents=True)
    (root / "source_citations").mkdir(parents=True)
    (root / "table_rows").mkdir(parents=True)
    (root / "graph_records").mkdir(parents=True)

    (root / "ocr_records" / "ocr.json").write_text(json.dumps({
        "records": [{
            "page_id": "t_p_120_1176_p000084",
            "ocr_text": "FIGURE 2 SHEET 1 P/N 120-41824-003",
            "ocr_engine": "tesseract",
            "ocr_confidence": 91.2,
        }]
    }), encoding="utf-8")

    (root / "visual_evidence" / "visual.json").write_text(json.dumps({
        "records": [{
            "page_id": "t_p_120_1176_p000084",
            "part_numbers": ["120-41824-003"],
            "figure_refs": ["figure 2 sheet 1"],
            "subject": "visual page associated with exact part",
        }, {
            "page_id": "t_p_120_1176_p000117",
            "part_numbers": ["120-41824-217"],
            "figure_refs": ["figure 8a"],
        }]
    }), encoding="utf-8")

    (root / "source_citations" / "source.json").write_text(json.dumps({
        "citations": [{
            "page_id": "t_p_120_1176_p000084",
            "field_name": "part_number",
            "normalized_value": "120-41824-003",
            "citation_ready": True,
            "source_trace_ready": True,
            "document": "EMB CMM ATA 25-21-00 REV.4",
        }]
    }), encoding="utf-8")

    (root / "table_rows" / "table.json").write_text(json.dumps({
        "rows": [{
            "page_id": "t_p_120_1176_p000085",
            "part_number": "120-41824-003",
            "item": "14",
            "nomenclature": "TEST COMPONENT",
        }]
    }), encoding="utf-8")

    (root / "graph_records" / "graph.json").write_text(json.dumps({
        "records": [{
            "page_id": "t_p_120_1176_p000084",
            "part_number": "120-41824-003",
            "relationship": "PART_ON_PAGE",
        }]
    }), encoding="utf-8")


def test_local_resolver_finds_direct_ocr_navigation_and_coverage(tmp_path):
    mod = load(HELPER, "retrieval_completion_v2_a")
    make_artifacts(tmp_path)
    resolver = mod.LocalArtifactResolver(tmp_path)
    result = resolver.resolve(
        query="Use OCR for 120-41824-003",
        route="ocr_scan_recovery",
        requested_parts=["120-41824-003"],
        seed_pages=["t_p_120_1176_p000084"],
    )
    assert result["quality_status"] == "PASS"
    assert result["direct_evidence"]
    assert result["ocr_evidence"]
    assert any(row["page_id"] == "t_p_120_1176_p000084" for row in result["navigation_leads"])
    assert result["unique_page_count"] >= 2
    assert all("120-41824-217" not in json.dumps(row) for row in result["aggregate_records"])


def test_navigation_renderer_keeps_matching_visual_page():
    mod = load(HELPER, "retrieval_completion_v2_b")
    envelope = SimpleNamespace(
        direct_evidence=[],
        candidate_evidence=[],
        semantic_guidance=[],
        visual_guidance=[{
            "page_id": "t_p_120_1176_p000084",
            "part_numbers": ["120-41824-003"],
            "figure_refs": ["figure 2 sheet 1"],
            "subject": "matching visual",
        }],
        authority_evidence=[],
        contradictions=[],
        coverage={"navigation_leads": []},
    )
    text = mod.render_navigation_answer(SimpleNamespace(), envelope, {"quality_status": "PASS"})
    assert "t_p_120_1176_p000084" in text
    assert "navigation guidance" in text.lower()


def test_ocr_renderer_reports_real_record_metadata():
    mod = load(HELPER, "retrieval_completion_v2_c")
    envelope = SimpleNamespace(
        direct_evidence=[],
        candidate_evidence=[],
        semantic_guidance=[],
        visual_guidance=[],
        authority_evidence=[],
        contradictions=[],
        coverage={"ocr_evidence": [{
            "page_id": "t_p_120_1176_p000084",
            "engine": "tesseract",
            "confidence": "91.2",
            "snippet": "P/N 120-41824-003",
            "citation_ready": False,
        }]},
    )
    text = mod.render_ocr_answer(SimpleNamespace(), envelope, {"quality_status": "PASS"})
    assert "tesseract" in text
    assert "91.2" in text
    assert "120-41824-003" in text


def test_aggregation_renderer_has_scope_and_counts():
    mod = load(HELPER, "retrieval_completion_v2_d")
    envelope = SimpleNamespace(
        direct_evidence=[],
        candidate_evidence=[],
        semantic_guidance=[],
        visual_guidance=[],
        authority_evidence=[],
        contradictions=[],
        coverage={
            "retrieval_completion": {
                "scanned_file_count": 10,
                "matched_file_count": 3,
                "coverage_complete_for_candidate_files": True,
            },
            "aggregate_records": [
                {"page_id": "t_p_1", "document": "DOC A", "source_type": "ocr"},
                {"page_id": "t_p_2", "document": "DOC A", "source_type": "visual"},
            ],
        },
    )
    text = mod.render_aggregation_answer(SimpleNamespace(), envelope, {"quality_status": "PASS"})
    assert "Unique matching pages currently resolved: 2" in text
    assert "Local artifact files scanned: 10" in text
    assert "currently indexed TRACE-Net artifact set" in text


def test_claim_renderer_keeps_every_claim_separate():
    mod = load(HELPER, "retrieval_completion_v2_e")
    envelope = SimpleNamespace(
        direct_evidence=[],
        candidate_evidence=[],
        semantic_guidance=[],
        visual_guidance=[],
        authority_evidence=[],
        contradictions=[],
        coverage={"claim_results": {
            "exact_identifier": {
                "status": "GUIDANCE_ONLY",
                "guidance": [{"page_id": "t_p_120_1176_p000084", "value": "120-41824-003"}],
            },
            "nomenclature": {"status": "NOT_FOUND", "guidance": []},
            "visual_identity": {
                "status": "GUIDANCE_ONLY",
                "guidance": [{"page_id": "t_p_120_1176_p000084", "value": "figure 2 sheet 1"}],
            },
            "authority": {"status": "NOT_FOUND", "guidance": []},
        }},
    )
    text = mod.render_claim_results(SimpleNamespace(), envelope, {"quality_status": "PASS"})
    assert "Exact part identity" in text
    assert "Nomenclature" in text
    assert "Figure / diagram" in text
    assert "Replacement / applicability authority" in text
    assert "not confirmed" in text


def test_semantic_route_suppresses_incidental_nomenclature_clue():
    boundary = load(BOUNDARY, "answer_boundary_v2")
    lines = boundary.query_clue_lines(
        "Find pages about corrosion prevention for passenger seat components.",
        {
            "exact_part_numbers": [],
            "ata_exact": [],
            "ata_prefix": None,
            "part_prefix": None,
            "part_contains": None,
            "part_suffix": None,
            "figures": [],
            "items": [],
            "page_ids": [],
            "nomenclature_terms": ["seat"],
            "manufacturer": None,
        },
        route="semantic_discovery",
    )
    assert not any("nomenclature clue" in line.lower() for line in lines)


def test_multi_route_keeps_nomenclature_clue_when_explicit():
    boundary = load(BOUNDARY, "answer_boundary_v2_multi")
    lines = boundary.query_clue_lines(
        "Find the nomenclature and figure.",
        {
            "exact_part_numbers": [],
            "ata_exact": [],
            "ata_prefix": None,
            "part_prefix": None,
            "part_contains": None,
            "part_suffix": None,
            "figures": [],
            "items": [],
            "page_ids": [],
            "nomenclature_terms": ["seat"],
            "manufacturer": None,
        },
        route="multi_question_research",
    )
    assert any("nomenclature clue" in line.lower() for line in lines)
