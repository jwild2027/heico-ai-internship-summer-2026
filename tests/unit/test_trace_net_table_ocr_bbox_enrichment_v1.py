import json
from pathlib import Path

from tiff.trace_net_table_ocr_bbox_enrichment_v1 import build_report, parse_tsv, parse_hocr


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_parse_tsv_extracts_word_boxes(tmp_path):
    p = tmp_path / "page.tsv"
    p.write_text("level\tleft\ttop\twidth\theight\tconf\ttext\n5\t10\t20\t30\t8\t90\t120-46137-001\n", encoding="utf-8")
    rows = parse_tsv(p)
    assert len(rows) == 1
    assert rows[0]["bbox"]["x0"] == 10


def test_parse_hocr_extracts_bbox_text(tmp_path):
    p = tmp_path / "page.hocr"
    p.write_text('<span class="ocrx_word" title="bbox 10 20 40 30">ABC</span>', encoding="utf-8")
    rows = parse_hocr(p)
    assert len(rows) == 1
    assert rows[0]["text"] == "ABC"


def test_build_report_matches_part_number_ocr_bbox(tmp_path):
    ocr_root = tmp_path / "ocr"
    ocr_root.mkdir()
    (ocr_root / "zip_page_000003_00000003.tsv").write_text(
        "level\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t100\t200\t120\t40\t90\t120-46137-001\n"
        "5\t240\t200\t80\t40\t90\tBRACKET\n",
        encoding="utf-8",
    )
    img = tmp_path / "zip_page_000003_00000003.tif"
    from PIL import Image
    Image.new("L", (1000, 1200), 255).save(img)
    tlg = {
        "quality_status": "PASS",
        "table_geometry_cards": [{
            "geometry_card_id": "g1", "page_id": "t_p_120_1176_p000003", "table_id": "t1", "table_type": "parts_list_table",
            "resolved_image_path": str(img), "domain_validation": {"part_numbers_sample": ["120-46137-001"]}
        }],
    }
    normalizer = {"quality_status": "PASS", "records": [{"page_id": "t_p_120_1176_p000003", "table_id": "t1", "text": "120-46137-001"}]}
    image_resolver = {"quality_status": "PASS", "table_image_resolution_cards": [{"page_id": "t_p_120_1176_p000003", "table_id": "t1", "resolved_image_path": str(img), "image_width": 1000, "image_height": 1200}]}
    bbox_resolver = {"quality_status": "PASS", "table_bbox_cards": [{"page_id": "t_p_120_1176_p000003", "table_id": "t1", "review_required": False}]}
    write_json(tmp_path / "tlg.json", tlg)
    write_json(tmp_path / "norm.json", normalizer)
    write_json(tmp_path / "img.json", image_resolver)
    write_json(tmp_path / "bbox.json", bbox_resolver)
    report = build_report(
        table_line_geometry_path=tmp_path / "tlg.json",
        table_cell_normalizer_path=tmp_path / "norm.json",
        table_image_resolver_path=tmp_path / "img.json",
        table_bbox_resolver_path=tmp_path / "bbox.json",
        ocr_root=ocr_root,
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        max_ocr_files_scanned=100,
        thresholds={
            "min_source_cards": 1, "min_enrichment_cards": 1, "min_crop_candidate_cards": 1,
            "max_unsafe_enrichment_cards": 0, "max_answer_permission_count": 0, "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_table_image_resolver_quality_pass": True,
            "require_table_bbox_resolver_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert report["quality_status"] == "PASS"
    card = report["table_ocr_bbox_enrichment_cards"][0]
    assert card["part_number_ocr_match_count"] == 1
    assert card["crop_candidate_ready"] is True
    assert card["bbox_source"] == "ocr_part_number_token_match"


def test_build_report_passes_with_missing_ocr_sidecar_when_threshold_zero(tmp_path):
    tlg = {"quality_status": "PASS", "table_geometry_cards": [{"geometry_card_id": "g1", "page_id": "p000001", "table_id": "t1"}]}
    normalizer = {"quality_status": "PASS"}
    write_json(tmp_path / "tlg.json", tlg)
    write_json(tmp_path / "norm.json", normalizer)
    report = build_report(
        table_line_geometry_path=tmp_path / "tlg.json",
        table_cell_normalizer_path=tmp_path / "norm.json",
        table_image_resolver_path=None,
        table_bbox_resolver_path=None,
        ocr_root=tmp_path / "missing",
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        max_ocr_files_scanned=10,
        thresholds={
            "min_source_cards": 1, "min_enrichment_cards": 1, "min_crop_candidate_cards": 0,
            "max_unsafe_enrichment_cards": 0, "max_answer_permission_count": 0, "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_table_image_resolver_quality_pass": False,
            "require_table_bbox_resolver_quality_pass": False,
            "require_no_answer_permission": True,
        },
    )
    assert report["quality_status"] == "PASS"
    assert "ocr_bbox_sidecar_not_found" in report["table_ocr_bbox_enrichment_cards"][0]["review_flags"]


def test_content_band_tightening_reduces_broad_ocr_union(tmp_path):
    from tiff.trace_net_table_ocr_bbox_enrichment_v1 import tighten_ocr_bbox_to_content_band, union_bboxes

    # Simulate OCR text matches scattered across a page, with a few header/footer
    # outliers that would make a raw OCR union too page-like.
    records = []
    for i in range(30):
        y = 300 + i * 30
        records.append({"text": f"row-{i}", "bbox": {"x0": 200, "y0": y, "x1": 900, "y1": y + 12, "width": 700, "height": 12}})
    records.extend([
        {"text": "header", "bbox": {"x0": 100, "y0": 0, "x1": 980, "y1": 20, "width": 880, "height": 20}},
        {"text": "footer", "bbox": {"x0": 100, "y0": 1180, "x1": 980, "y1": 1200, "width": 880, "height": 20}},
    ])
    broad = union_bboxes([r["bbox"] for r in records], pad_ratio=0.045, width=1000, height=1200)
    tightened, diag = tighten_ocr_bbox_to_content_band(records, broad, width=1000, height=1200, table_type="parts_list_table")

    assert diag["ocr_content_band_tightening_applied"] is True
    assert tightened is not None
    assert diag["ocr_content_band_tightened_coverage_ratio"] < diag["ocr_content_band_original_coverage_ratio"]
    assert tightened["y0"] > 0
    assert tightened["y1"] < 1200


def test_build_report_records_content_band_fields_for_broad_ocr_bbox(tmp_path):
    ocr_root = tmp_path / "ocr"
    ocr_root.mkdir()
    rows = ["level\tleft\ttop\twidth\theight\tconf\ttext"]
    rows.append("5\t100\t0\t850\t20\t90\tEFFECTIVITY")
    for i in range(25):
        rows.append(f"5\t220\t{260+i*25}\t500\t18\t90\tTABLETOKEN{i}")
    rows.append("5\t100\t1180\t850\t20\t90\tFOOTER")
    (ocr_root / "zip_page_000005_00000005.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    img = tmp_path / "zip_page_000005_00000005.tif"
    from PIL import Image
    Image.new("L", (1000, 1200), 255).save(img)
    tlg = {
        "quality_status": "PASS",
        "table_geometry_cards": [{
            "geometry_card_id": "g1", "page_id": "t_p_120_1176_p000005", "table_id": "t1", "table_type": "list_of_effective_pages",
            "resolved_image_path": str(img)
        }],
    }
    normalizer = {"quality_status": "PASS", "records": [
        {"page_id": "t_p_120_1176_p000005", "table_id": "t1", "text": token}
        for token in (["EFFECTIVITY", "FOOTER"] + [f"TABLETOKEN{i}" for i in range(25)])
    ]}
    image_resolver = {"quality_status": "PASS", "table_image_resolution_cards": [{"page_id": "t_p_120_1176_p000005", "table_id": "t1", "resolved_image_path": str(img), "image_width": 1000, "image_height": 1200}]}
    bbox_resolver = {"quality_status": "PASS", "table_bbox_cards": [{"page_id": "t_p_120_1176_p000005", "table_id": "t1", "review_required": False}]}
    write_json(tmp_path / "tlg.json", tlg)
    write_json(tmp_path / "norm.json", normalizer)
    write_json(tmp_path / "img.json", image_resolver)
    write_json(tmp_path / "bbox.json", bbox_resolver)

    report = build_report(
        table_line_geometry_path=tmp_path / "tlg.json",
        table_cell_normalizer_path=tmp_path / "norm.json",
        table_image_resolver_path=tmp_path / "img.json",
        table_bbox_resolver_path=tmp_path / "bbox.json",
        ocr_root=ocr_root,
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        max_ocr_files_scanned=100,
        thresholds={
            "min_source_cards": 1, "min_enrichment_cards": 1, "min_crop_candidate_cards": 1,
            "max_unsafe_enrichment_cards": 0, "max_answer_permission_count": 0, "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_table_image_resolver_quality_pass": True,
            "require_table_bbox_resolver_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert report["quality_status"] == "PASS"
    card = report["table_ocr_bbox_enrichment_cards"][0]
    assert card["content_band_tightening_applied"] is True
    assert card["bbox_coverage_ratio"] < card["original_bbox_coverage_ratio"]
    assert report["summary"]["content_band_tightening_applied_card_count"] == 1
