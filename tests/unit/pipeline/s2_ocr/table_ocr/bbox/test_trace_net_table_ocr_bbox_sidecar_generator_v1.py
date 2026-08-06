import json
from pathlib import Path

from tiff.trace_net_table_ocr_bbox_sidecar_generator_v1 import (
    GeneratorConfig,
    build_sidecar_generator_report,
    find_part_number_matches,
    group_word_records_into_lines,
    load_source_cards,
    parse_tesseract_tsv,
)
from tiff.trace_net_table_ocr_bbox_sidecar_generator_v1_quality import SidecarQualityThresholds


def test_parse_tesseract_tsv_filters_blank_words():
    tsv = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n" \
          "5\t1\t1\t1\t1\t1\t10\t20\t30\t40\t91\t120-20970-001\n" \
          "5\t1\t1\t1\t1\t2\t50\t20\t10\t40\t-1\t\n"
    rows = parse_tesseract_tsv(tsv)
    assert len(rows) == 1
    assert rows[0]["text"] == "120-20970-001"
    assert rows[0]["bbox"]["x1"] == 40


def test_group_lines_and_find_split_part_number():
    words = [
        {"page_num":1,"block_num":1,"par_num":1,"line_num":1,"word_num":1,"text":"120-1","conf":80,"bbox":{"x0":10,"y0":10,"x1":50,"y1":20}},
        {"page_num":1,"block_num":1,"par_num":1,"line_num":1,"word_num":2,"text":"7588-001","conf":80,"bbox":{"x0":55,"y0":10,"x1":120,"y1":20}},
    ]
    lines = group_word_records_into_lines(words)
    matches = find_part_number_matches(lines)
    assert [m["part_number"] for m in matches] == ["120-17588-001"]
    assert matches[0]["match_type"] == "split_token_repair"


def test_load_source_cards_from_resolver():
    payload = {
        "table_image_resolution_cards": [
            {"page_id":"p1","table_id":"t1","table_type":"parts_list_table","resolved_image_path":"a.tif","image_resolution_confidence":1.0},
            {"page_id":"p1","table_id":"t1","table_type":"parts_list_table","resolved_image_path":"a.tif"},
            {"page_id":"p2","table_id":"t2"},
        ]
    }
    cards = load_source_cards(payload)
    assert len(cards) == 1
    assert cards[0]["page_id"] == "p1"


def test_build_report_handles_missing_image_without_store_writes(tmp_path):
    resolver_path = tmp_path / "resolver.json"
    resolver_path.write_text(json.dumps({
        "quality_status":"PASS",
        "table_image_resolution_cards":[{"page_id":"p1","table_id":"t1","resolved_image_path":"missing.tif"}],
    }), encoding="utf-8")
    config = GeneratorConfig(
        table_image_resolver_path=resolver_path,
        output_dir=tmp_path / "out",
        image_root=tmp_path,
        max_pages=1,
    )
    report = build_sidecar_generator_report(
        config,
        SidecarQualityThresholds(
            min_source_cards=1,
            min_attempted_pages=1,
            min_generated_sidecar_pages=0,
            min_ocr_word_records=0,
            require_table_image_resolver_quality_pass=True,
            require_no_answer_permission=True,
        ),
        quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["source_table_image_card_count"] == 1
    assert report["summary"]["generated_sidecar_page_count"] == 0
    assert report["summary"]["postgres_write_attempt_count"] == 0
