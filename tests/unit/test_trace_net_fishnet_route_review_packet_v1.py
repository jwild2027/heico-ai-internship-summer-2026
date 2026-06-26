import json
from pathlib import Path

from tiff.trace_net_fishnet_route_review_packet_v1 import (
    build_review_packet,
    route_pair,
    select_review_records,
    ReviewSelectionConfig,
)


def _record(page, current, fishnet, *, status="disagree", conf=0.5, text=100, boxes=10, review=False, best=None):
    return {
        "page_id": f"source_p{page:06d}",
        "current_route_page_id": f"t_p_120_1176_p{page:06d}",
        "current_route": current,
        "fishnet_route_candidate": fishnet,
        "fishnet_best_route_candidate_before_review": best or fishnet,
        "agreement_status": status,
        "review_severity": "high" if status == "high_confidence_disagreement" else ("review" if review else "medium"),
        "fishnet_review_required": review,
        "fishnet_review_reason_codes": ["low_route_margin"] if review else [],
        "fishnet_route_confidence": conf,
        "fishnet_route_scores": {"normal_text": conf, "table": 0.1},
        "fishnet_route_adjusted_scores": {"normal_text": conf, "table": 0.1},
        "fishnet_reason_counts": {"ocr_cell_count": 5},
        "fishnet_ocr_engine_status": "ok" if text else "empty",
        "fishnet_ocr_text_length": text,
        "fishnet_ocr_word_count": max(0, text // 8),
        "fishnet_ocr_word_box_count": boxes,
        "fishnet_ocr_sample_text": "sample text",
        "reason_codes": [f"current_{current}_vs_fishnet_{fishnet}"],
        "page_id_match_strategy": "alias",
    }


def test_route_pair_normalizes_missing():
    assert route_pair("blank_candidate", "normal_text") == "blank_candidate->normal_text"
    assert route_pair(None, "table") == "missing->table"


def test_select_review_records_includes_high_confidence_and_representatives(tmp_path):
    records = [
        _record(4, "image_visual", "normal_text", status="high_confidence_disagreement", conf=0.94, text=892, boxes=129),
        _record(466, "blank_candidate", "normal_text", status="high_confidence_disagreement", conf=0.88, text=941, boxes=147),
        _record(8, "table", "review_required", status="fishnet_review_required", conf=0.0, text=2103, boxes=371, review=True, best="table"),
        _record(20, "blank_candidate", "table", status="disagree", conf=0.4, text=1000, boxes=100),
    ]
    selected = select_review_records(
        records,
        config=ReviewSelectionConfig(high_confidence_limit=10, representative_per_pair=2, review_required_limit=2),
        overlays_dir=tmp_path,
    )
    pages = {r["page_id"] for r in selected}
    assert "source_p000004" in pages
    assert "source_p000466" in pages
    assert "source_p000008" in pages
    assert "source_p000020" in pages
    assert all(r["route_change_authorized"] is False for r in selected)
    assert all(r["answer_permission"] is False for r in selected)


def test_build_review_packet_writes_json_jsonl_summary_quality_markdown(tmp_path):
    workbench = {
        "quality_status": "PASS",
        "summary": {
            "comparison_record_count": 4,
            "agreement_count": 0,
            "disagreement_count": 3,
            "high_confidence_disagreement_count": 2,
            "review_required_count": 1,
            "total_fishnet_ocr_text_length": 493498,
            "total_fishnet_ocr_word_box_count": 83741,
        },
        "records": [
            _record(4, "image_visual", "normal_text", status="high_confidence_disagreement", conf=0.94, text=892, boxes=129),
            _record(466, "blank_candidate", "normal_text", status="high_confidence_disagreement", conf=0.88, text=941, boxes=147),
            _record(8, "table", "review_required", status="fishnet_review_required", conf=0.0, text=2103, boxes=371, review=True, best="table"),
            _record(20, "blank_candidate", "table", status="disagree", conf=0.4, text=1000, boxes=100),
        ],
    }
    workbench_path = tmp_path / "workbench.json"
    workbench_path.write_text(json.dumps(workbench), encoding="utf-8")
    out = tmp_path / "out"
    payload = build_review_packet(workbench_report=workbench_path, output_dir=out, high_confidence_limit=10)
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["review_record_count"] >= 3
    assert payload["summary"]["high_confidence_review_record_count"] == 2
    assert (out / "trace_net_fishnet_route_review_packet_v1.json").exists()
    assert (out / "trace_net_fishnet_route_review_packet_v1_records.jsonl").exists()
    assert (out / "trace_net_fishnet_route_review_packet_v1_summary.json").exists()
    assert (out / "trace_net_fishnet_route_review_packet_v1_quality.json").exists()
    assert (out / "trace_net_fishnet_route_review_packet_v1.md").exists()


def test_overlay_candidates_preserve_likely_path(tmp_path):
    workbench = {
        "quality_status": "PASS",
        "summary": {},
        "records": [_record(4, "image_visual", "normal_text", status="high_confidence_disagreement", conf=0.94, text=892, boxes=129)],
    }
    workbench_path = tmp_path / "workbench.json"
    workbench_path.write_text(json.dumps(workbench), encoding="utf-8")
    overlay_dir = tmp_path / "overlays"
    overlay_dir.mkdir()
    payload = build_review_packet(workbench_report=workbench_path, output_dir=tmp_path / "out", overlays_dir=overlay_dir)
    record = payload["records"][0]
    assert record["overlay_candidates"]
    assert "source_p000004" in record["overlay_candidates"][0]
