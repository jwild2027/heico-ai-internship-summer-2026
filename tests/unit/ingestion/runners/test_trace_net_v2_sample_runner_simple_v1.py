from __future__ import annotations
import json
from pathlib import Path
from tiff.trace_net_v2_sample_runner_simple_v1 import build_sample, check_report, validate_card, wanted_id

def test_wanted_id() -> None:
    assert wanted_id(48) == "t_p_120_1176_p000048"

def test_validate_blocks_answer_permission() -> None:
    card = {"page_id":"p1","role":"table","subrole":"general","confidence":"medium","short_summary":"s","retrieval_summary":"r","answerable_questions":[],"retrieval_cues":[],"source_grounding":{},"authority":{"can_answer_directly": True},"prompt_version":"v"}
    assert validate_card(card)["quality_status"] == "FAIL"

def test_build_sample_five_records(tmp_path: Path) -> None:
    ctx = tmp_path / "page_contexts.json"
    data = {f"t_p_120_1176_p{n:06d}": {"page_id": f"t_p_120_1176_p{n:06d}", "role": "table", "summary": f"Sample page {n} parts list", "text": f"FIGURE {n} PASSENGER SEAT PARTS 120-36833-00{n}", "source_url": f"file:///sample/{n}.tif"} for n in range(1,6)}
    ctx.write_text(json.dumps(data), encoding="utf-8")
    report = build_sample(ctx, tmp_path / "out", max_pages=5)
    assert report["quality_status"] == "PASS"
    assert report["summary"]["sample_record_count"] == 5
    assert all(r["guidance_only"] is True for r in report["records"])
    assert all(r["authority"]["can_answer_directly"] is False for r in report["records"])
    assert all("v3_preview" in r for r in report["records"])

def test_check_report(tmp_path: Path) -> None:
    ctx = tmp_path / "page_contexts.json"
    ctx.write_text(json.dumps([{ "page_id": f"t_p_120_1176_p{n:06d}", "summary": f"page {n}", "ocr_text": "OCR PART 120-36833-001"} for n in range(1,6)]), encoding="utf-8")
    report = build_sample(ctx, tmp_path / "out", max_pages=5)
    q = check_report(tmp_path / "out" / "trace_net_v2_sample_runner_simple_v1.json", tmp_path / "out" / "q.json", min_records=5)
    assert q["quality_status"] == "PASS"
