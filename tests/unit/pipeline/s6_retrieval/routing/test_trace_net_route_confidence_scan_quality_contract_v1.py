from __future__ import annotations

import pytest

from tiff.trace_net_route_confidence_resolver_v1 import _resolve_record


def test_route_resolver_preserves_page_type_and_attaches_quality_metadata():
    record = {
        "page_id": "t_p_test_p000005",
        "page_number": 5,
        "accepted_route": "table",
        "ocr_text": (
            "LIST OF EFFECTIVE PAGES PAGE DATE CHAPTER SECTION SUBJECT "
            "25-LEP Apr 10/06 25-21-00 607 Sep 30/98"
        ),
        "image_quality_metrics": {
            "sharpness_score": 0.81,
            "edge_spread_pixels": 1.0,
            "local_contrast": 0.42,
            "width": 3205,
            "height": 4146,
            "dpi": 377,
            "layout_reading_order_conflict": True,
        },
    }
    result = _resolve_record(record, high_threshold=85.0, medium_threshold=60.0)
    assert result["primary_route"] in {"table_or_index", "review_required"}
    assert result["primary_route"] != "blurry"
    assert result["scan_quality_state"] == "clear"
    assert result["blur_detected"] is False
    assert result["scan_quality"]["layout_reconstruction_issue"] is True
    assert result["scan_quality"]["page_route"] == result["primary_route"]


def test_route_resolver_rejects_legacy_blurry_page_classification():
    record = {
        "page_id": "p1",
        "accepted_route": "blurry",
        "ocr_text": "normal readable page text with several words",
    }
    with pytest.raises(ValueError, match="scan quality cannot be used as a page route"):
        _resolve_record(record, high_threshold=85.0, medium_threshold=60.0)
