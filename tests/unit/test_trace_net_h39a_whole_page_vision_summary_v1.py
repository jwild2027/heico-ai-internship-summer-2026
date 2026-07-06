import json
from pathlib import Path

from tiff.trace_net_h39a_whole_page_vision_summary_v1 import (
    build_whole_page_vision_summary,
    check_whole_page_vision_summary,
    discover_image_visual_pages,
    extract_page_id,
    find_image_for_page,
    looks_like_bad_page_id,
)


def test_page_id_filters_metadata():
    assert looks_like_bad_page_id("metadata_page_000001")
    assert looks_like_bad_page_id("source_p000001")
    assert not looks_like_bad_page_id("t_p_120_1176_p000315")
    assert extract_page_id({"page_id": "metadata_page_000001"}) == ""


def test_discover_real_image_visual_page(tmp_path):
    pack = tmp_path / "visual.json"
    pack.write_text(json.dumps({
        "records": [
            {"page_id": "metadata_page_000001", "route": "image_visual"},
            {"page_id": "t_p_120_1176_p000315", "route": "image_visual", "page_number": 315},
        ]
    }), encoding="utf-8")

    pages = discover_image_visual_pages(pack, trace_dir=tmp_path)
    assert [p["page_id"] for p in pages] == ["t_p_120_1176_p000315"]


def test_find_image_uses_exact_page_token(tmp_path):
    root = tmp_path / "images"
    root.mkdir()
    good = root / "t_p_120_1176_p000315.tif"
    bad = root / "003_t_p_120_1176_p000006_normtable_preview.png"
    good.write_bytes(b"fake")
    bad.write_bytes(b"fake")

    page = {"page_id": "t_p_120_1176_p000315", "page_number": "315"}
    found = find_image_for_page(page, [root])
    assert found == good


def test_artifact_build_and_check(tmp_path):
    root = tmp_path / "images"
    root.mkdir()
    image = root / "t_p_120_1176_p000315.png"
    image.write_bytes(b"fake-png")

    pack = tmp_path / "visual.json"
    pack.write_text(json.dumps({
        "records": [
            {"page_id": "t_p_120_1176_p000315", "route": "image_visual", "page_number": 315}
        ]
    }), encoding="utf-8")

    result = build_whole_page_vision_summary(
        image_visual_evidence_pack=pack,
        output_dir=tmp_path / "out",
        image_roots=str(root),
        trace_dir=tmp_path,
        llm_mode="artifact",
        max_pages=1,
        min_records=1,
        min_pass=1,
        progress=False,
    )
    assert result["quality_status"] == "PASS"
    check = check_whole_page_vision_summary(
        tmp_path / "out" / "trace_net_h39a_whole_page_vision_summary_v1.json",
        require_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert check["quality_status"] == "PASS"
