from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path("scripts/trace_net_h30_layout_aware_ocr_v1.py")


def load_module(name: str = "trace_net_h30_layout_aware_ocr_test"):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_q17_flat_ocr_becomes_two_conservative_rows():
    module = load_module("layout_q17")
    result = module.reconstruct_layout_aware_ocr(
        "- Apr 10/06 25-21-00 607 Sep 30/98 25-LEP"
    )
    assert result["reconstruction_available"]
    assert result["table_kind"] == "list_of_effective_pages"
    assert result["flattened_multi_column_reading_order"]
    assert result["blur_detected"] is False
    rows = result["rows"]
    assert any(row["section"] == "25-21-00" and row["page"] == "607" and row["date"] == "Sep 30/98" for row in rows)
    assert any(row["section"] == "25-LEP" and row["date"] == "Apr 10/06" for row in rows)


def test_rendered_q17_summary_is_readable():
    module = load_module("layout_render")
    result = module.reconstruct_layout_aware_ocr(
        "25-LIST OF EFFECTIVE PAGES Page 1 Apr 10/06 25-21-00 607 Sep 30/98 25-LEP"
    )
    text = module.render_layout_reconstruction(result)
    assert "List of Effective Pages table" in text
    assert "ATA 25-21-00" in text
    assert "manual page 607" in text
    assert "Section 25-LEP" in text
    assert "blurry" not in text.lower()


def test_normal_prose_is_not_forced_into_table_reconstruction():
    module = load_module("layout_prose")
    result = module.reconstruct_layout_aware_ocr(
        "Remove the fastener and inspect the surrounding structure for damage."
    )
    assert result["reconstruction_available"] is False
    assert result["rows"] == []
    assert result["scan_quality_inferred"] is False


def test_query_or_route_wording_cannot_create_blur_claim():
    module = load_module("layout_blur_guard")
    result = module.reconstruct_layout_aware_ocr(
        "25-21-00 607 Sep 30/98 25-LEP Apr 10/06",
        page_route="blurry scanned page",
    )
    assert result["blur_detected"] is False
    assert result["blur_claim_allowed"] is False
    assert result["scan_quality_inferred"] is False


def test_coordinate_rows_take_priority():
    module = load_module("layout_coordinates")
    words = [
        {"text": "25-LEP", "left": 10, "top": 10, "width": 50, "height": 10},
        {"text": "Apr", "left": 150, "top": 10, "width": 25, "height": 10},
        {"text": "10/06", "left": 180, "top": 10, "width": 35, "height": 10},
        {"text": "25-21-00", "left": 10, "top": 40, "width": 60, "height": 10},
        {"text": "607", "left": 100, "top": 40, "width": 25, "height": 10},
        {"text": "Sep", "left": 150, "top": 40, "width": 25, "height": 10},
        {"text": "30/98", "left": 180, "top": 40, "width": 35, "height": 10},
    ]
    result = module.reconstruct_layout_aware_ocr("flattened text", word_boxes=words)
    assert result["reconstruction_basis"] == "word_coordinates"
    assert result["reconstruction_confidence"] == "high"
    assert result["requires_image_verification"] is False
    assert len(result["reconstructed_lines"]) == 2


def test_health_contract_is_read_only_and_no_extra_llm_call():
    module = load_module("layout_health")
    report = module.health()
    assert report["read_only"] is True
    assert report["derived_layout_is_guidance_only"] is True
    assert report["adds_gemma_call"] is False
    assert report["changes_retrieval"] is False
    assert report["source_truth_mutation_allowed"] is False
