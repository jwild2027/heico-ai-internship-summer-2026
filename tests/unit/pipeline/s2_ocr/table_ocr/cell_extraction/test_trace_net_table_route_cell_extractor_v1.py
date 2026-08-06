import json
from pathlib import Path

from tiff.trace_net_table_route_cell_extractor_v1 import (
    build_report,
    group_tokens_into_lines,
    split_line_into_cells,
    normalize_bbox,
)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_line_and_cell_grouping_extracts_cells():
    tokens = [
        {"text": "FIG", "bbox": {"x0": 10, "y0": 10, "x1": 30, "y1": 20}},
        {"text": "ITEM", "bbox": {"x0": 100, "y0": 10, "x1": 140, "y1": 20}},
        {"text": "PART", "bbox": {"x0": 260, "y0": 10, "x1": 300, "y1": 20}},
        {"text": "1", "bbox": {"x0": 12, "y0": 40, "x1": 22, "y1": 50}},
        {"text": "120-46137-001", "bbox": {"x0": 260, "y0": 40, "x1": 360, "y1": 50}},
    ]
    lines = group_tokens_into_lines(tokens)
    assert len(lines) == 2
    cells = split_line_into_cells(lines[0])
    assert len(cells) == 3


def test_build_report_uses_ocr_and_skips_review_only(tmp_path):
    reconstructor = {
        "quality_status": "PASS",
        "table_full_enclosure_bbox_reconstructor_records": [
            {
                "full_enclosure_record_id": "r1",
                "page_id": "t_p_120_1176_p000001",
                "table_id": "t1",
                "final_table_bbox": {"x0": 0, "y0": 0, "x1": 500, "y1": 700},
                "final_table_bbox_source": "full_page_bbox_step0",
                "full_table_enclosure_bbox_ready": True,
                "table_bbox_review_only": False,
            },
            {
                "full_enclosure_record_id": "r2",
                "page_id": "t_p_120_1176_p000002",
                "table_id": "t2",
                "final_table_bbox": {"x0": 0, "y0": 0, "x1": 500, "y1": 700},
                "final_table_bbox_source": "review_only_image_or_non_table_bbox_preserved",
                "full_table_enclosure_bbox_ready": False,
                "table_bbox_review_only": True,
            },
        ],
    }
    ocr_path = tmp_path / "ocr" / "t_p_120_1176_p000001.tsv"
    ocr_path.parent.mkdir(parents=True)
    ocr_path.write_text(
        "left\ttop\twidth\theight\ttext\n"
        "10\t10\t35\t10\tFIG\n"
        "90\t10\t40\t10\tITEM\n"
        "210\t10\t80\t10\tPART NUMBER\n"
        "10\t40\t20\t10\t1\n"
        "210\t40\t120\t10\t120-46137-001\n",
        encoding="utf-8",
    )
    enrichment = {
        "quality_status": "PASS",
        "table_ocr_bbox_enrichment_cards": [
            {
                "page_id": "t_p_120_1176_p000001",
                "table_id": "t1",
                "ocr_source_files_sample": [str(ocr_path)],
            }
        ],
    }
    scoped = {"quality_status": "PASS", "scoped_table_records": []}
    recon_path = tmp_path / "recon.json"
    enrich_path = tmp_path / "enrich.json"
    scoped_path = tmp_path / "scoped.json"
    write_json(recon_path, reconstructor)
    write_json(enrich_path, enrichment)
    write_json(scoped_path, scoped)
    report = build_report(
        table_full_enclosure_bbox_reconstructor_path=recon_path,
        table_ocr_bbox_enrichment_path=enrich_path,
        table_bbox_scoped_cell_extraction_path=scoped_path,
        ocr_root=ocr_path.parent,
        output_dir=tmp_path / "out",
        max_ocr_files_per_table=5,
        max_rows_per_table=50,
        allow_legacy_fallback=False,
        thresholds={
            "min_source_table_bbox_records": 2,
            "min_extraction_records": 2,
            "min_extraction_ready_tables": 1,
            "min_review_only_skipped": 1,
            "min_cell_extraction_attempted": 1,
            "min_cell_extraction_success_records": 1,
            "min_row_records": 2,
            "min_cell_records": 3,
            "min_value_records": 3,
            "max_unsafe_records": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_full_enclosure_bbox_reconstructor_quality_pass": True,
            "require_table_ocr_bbox_enrichment_quality_pass": True,
            "require_table_bbox_scoped_cell_extraction_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["extraction_ready_table_count"] == 1
    assert summary["review_only_skipped_count"] == 1
    assert summary["table_value_record_count"] >= 3
    assert summary["part_number_candidate_count"] >= 1


def test_normalize_bbox_accepts_xywh():
    box = normalize_bbox({"x": 1, "y": 2, "width": 3, "height": 4})
    assert box["x1"] == 4
    assert box["y1"] == 6


def test_build_report_selects_best_single_ocr_file_and_deduplicates(tmp_path):
    reconstructor = {
        "quality_status": "PASS",
        "table_full_enclosure_bbox_reconstructor_records": [
            {
                "full_enclosure_record_id": "r1",
                "page_id": "t_p_120_1176_p000001",
                "table_id": "t1",
                "final_table_bbox": {"x0": 0, "y0": 0, "x1": 500, "y1": 700},
                "final_table_bbox_source": "full_page_bbox_step0",
                "full_table_enclosure_bbox_ready": True,
                "table_bbox_review_only": False,
            }
        ],
    }
    noisy_path = tmp_path / "ocr" / "noisy_t_p_120_1176_p000001.tsv"
    good_path = tmp_path / "ocr" / "good_t_p_120_1176_p000001.tsv"
    noisy_path.parent.mkdir(parents=True)
    noisy_path.write_text(
        "left\ttop\twidth\theight\ttext\n"
        "10\t10\t20\t10\tEMBRAER\n"
        "10\t30\t20\t10\tEMBRAER\n"
        "10\t50\t20\t10\tEMBRAER\n",
        encoding="utf-8",
    )
    good_path.write_text(
        "left\ttop\twidth\theight\ttext\n"
        "10\t10\t35\t10\tFIG\n"
        "90\t10\t40\t10\tITEM\n"
        "210\t10\t80\t10\tPART NUMBER\n"
        "10\t40\t20\t10\t1\n"
        "210\t40\t120\t10\t120-46137-001\n"
        "210\t40\t120\t10\t120-46137-001\n",
        encoding="utf-8",
    )
    enrichment = {
        "quality_status": "PASS",
        "table_ocr_bbox_enrichment_cards": [
            {
                "page_id": "t_p_120_1176_p000001",
                "table_id": "t1",
                "ocr_source_files_sample": [str(noisy_path), str(good_path)],
            }
        ],
    }
    scoped = {"quality_status": "PASS", "scoped_table_records": []}
    recon_path = tmp_path / "recon.json"; enrich_path = tmp_path / "enrich.json"; scoped_path = tmp_path / "scoped.json"
    write_json(recon_path, reconstructor); write_json(enrich_path, enrichment); write_json(scoped_path, scoped)

    report = build_report(
        table_full_enclosure_bbox_reconstructor_path=recon_path,
        table_ocr_bbox_enrichment_path=enrich_path,
        table_bbox_scoped_cell_extraction_path=scoped_path,
        ocr_root=noisy_path.parent,
        output_dir=tmp_path / "out",
        max_ocr_files_per_table=5,
        max_rows_per_table=50,
        allow_legacy_fallback=False,
        thresholds={
            "min_source_table_bbox_records": 1,
            "min_extraction_records": 1,
            "min_extraction_ready_tables": 1,
            "min_cell_extraction_attempted": 1,
            "min_cell_extraction_success_records": 1,
            "min_row_records": 2,
            "min_cell_records": 3,
            "min_value_records": 3,
            "max_ocr_selected_files_per_table_average": 1.0,
            "max_unsafe_records": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_full_enclosure_bbox_reconstructor_quality_pass": True,
            "require_table_ocr_bbox_enrichment_quality_pass": True,
            "require_table_bbox_scoped_cell_extraction_quality_pass": True,
            "require_no_answer_permission": True,
        },
        ocr_file_selection="best",
        deduplicate_ocr_tokens=True,
    )
    assert report["quality_status"] == "PASS"
    record = report["table_route_cell_extraction_records"][0]
    assert record["ocr_candidate_file_count"] == 2
    assert record["ocr_selected_file_count"] == 1
    assert record["ocr_file_selection_reason"] == "best_single_ocr_file_by_table_score"
    assert record["ocr_duplicate_token_removed_count"] == 1
    assert "good_t_p_120_1176_p000001.tsv" in record["ocr_source_files_sample"][0]

from tiff.trace_net_table_route_cell_extractor_v1 import (
    classify_ocr_source_file,
    collapse_repeated_cell_groups,
)


def test_classify_ocr_source_file_prefers_raw_over_match_sidecar():
    assert classify_ocr_source_file('t_p_120_1176_p000003__zip_page_000003_00000003.tsv') == 'raw_ocr_sidecar'
    assert classify_ocr_source_file('t_p_120_1176_p000003__zip_page_000003_00000003_part_number_matches.jsonl') == 'derived_match_sidecar'


def test_repeated_cell_groups_are_collapsed():
    cell = [{"text": "120-36833-001 120-36833-003", "bbox": {"x0": 1, "y0": 1, "x1": 10, "y1": 10}}]
    cells, removed = collapse_repeated_cell_groups([cell, list(cell), [{"text": "120-36833-005", "bbox": {"x0": 20, "y0": 1, "x1": 40, "y1": 10}}]])
    assert removed == 1
    assert len(cells) == 2

from tiff.trace_net_table_route_cell_extractor_v1 import (
    classify_ocr_source_detail,
    load_ocr_tokens,
)


def test_classify_ocr_source_detail_distinguishes_tsv_and_line_jsonl():
    assert classify_ocr_source_detail('t_p_120_1176_p000005__zip_page_000005_00000005.tsv') == 'raw_tsv_word_ocr_sidecar'
    assert classify_ocr_source_detail('t_p_120_1176_p000005__zip_page_000005_00000005_ocr_lines.jsonl') == 'raw_line_ocr_sidecar'
    assert classify_ocr_source_detail('t_p_120_1176_p000005__zip_page_000005_00000005_part_number_matches.jsonl') == 'derived_match_sidecar'


def test_best_ocr_selection_prefers_token_level_tsv_over_line_jsonl(tmp_path):
    ocr_root = tmp_path / 'ocr'
    ocr_root.mkdir()
    tsv_path = ocr_root / 't_p_120_1176_p000005__zip_page_000005_00000005.tsv'
    line_path = ocr_root / 't_p_120_1176_p000005__zip_page_000005_00000005_ocr_lines.jsonl'
    # TSV has token/word geometry suitable for cell splitting.
    tsv_lines = ['left\ttop\twidth\theight\ttext']
    for i in range(12):
        y = 20 + i * 20
        tsv_lines.append(f'10\t{y}\t30\t10\tPAGE')
        tsv_lines.append(f'80\t{y}\t60\t10\t25-21-00')
        tsv_lines.append(f'180\t{y}\t35\t10\tREV')
    tsv_path.write_text('\n'.join(tsv_lines), encoding='utf-8')
    # Line JSONL has plausible table lines but coarser geometry.
    line_records = []
    for i in range(18):
        y = 20 + i * 18
        line_records.append({'text': 'PAGE 25-21-00 REV', 'bbox': {'x0': 5, 'y0': y, 'x1': 260, 'y1': y + 10}})
    line_path.write_text('\n'.join(json.dumps(r) for r in line_records), encoding='utf-8')
    tokens, files, diagnostics = load_ocr_tokens(
        {'ocr_source_files_sample': [str(line_path), str(tsv_path)]},
        't_p_120_1176_p000005',
        ocr_root,
        10,
        final_bbox={'x0': 0, 'y0': 0, 'x1': 500, 'y1': 500},
        ocr_file_selection='best',
    )
    assert files == [str(tsv_path).replace('\\', '/')]
    assert diagnostics['ocr_file_selection_reason'] == 'best_token_level_raw_ocr_file_by_table_score'
    assert diagnostics['ocr_selected_source_detail'] == 'raw_tsv_word_ocr_sidecar'
    assert diagnostics['ocr_line_raw_candidate_file_count'] == 1
    assert len(tokens) >= 30

from tiff.trace_net_table_route_cell_extractor_v1 import (
    detect_table_template,
    TEMPLATE_LIST_EFFECTIVE_PAGES,
    TEMPLATE_PART_NUMBER_COVERAGE,
)


def test_template_detection_identifies_part_number_coverage_list():
    rows = [
        {"row_id": "r0", "row_text": "This publication covers the following part numbers:", "looks_like_header": True},
        {"row_id": "r1", "row_text": "120-36833-001 120-36833-003 120-36833-005", "part_number_count": 3},
    ]
    cells = []
    values = [
        {"normalized_value": "This publication covers the following part numbers:", "value_kind": "header"},
        {"normalized_value": "120-36833-001", "value_kind": "part_number"},
        {"normalized_value": "120-36833-003", "value_kind": "part_number"},
        {"normalized_value": "120-36833-005", "value_kind": "part_number"},
        {"normalized_value": "120-36833-501", "value_kind": "part_number"},
        {"normalized_value": "120-36834-001", "value_kind": "part_number"},
        {"normalized_value": "120-36834-003", "value_kind": "part_number"},
        {"normalized_value": "120-36834-005", "value_kind": "part_number"},
        {"normalized_value": "120-36834-501", "value_kind": "part_number"},
        {"normalized_value": "120-41824-001", "value_kind": "part_number"},
        {"normalized_value": "120-41824-003", "value_kind": "part_number"},
        {"normalized_value": "120-41824-005", "value_kind": "part_number"},
        {"normalized_value": "120-41824-007", "value_kind": "part_number"},
    ]
    template = detect_table_template(rows, cells, values)
    assert template["table_template_type"] == TEMPLATE_PART_NUMBER_COVERAGE
    assert "part_list_many_part_numbers" in template["table_template_signals"]


def test_template_detection_identifies_list_of_effective_pages():
    rows = [
        {"row_id": "r0", "row_text": "LIST OF EFFECTIVE PAGES", "looks_like_header": True},
        {"row_id": "r1", "row_text": "Page Date Rev", "looks_like_header": True},
        {"row_id": "r2", "row_text": "25-21-00 01 4", "part_number_count": 0},
    ]
    cells = []
    values = [
        {"normalized_value": "LIST OF EFFECTIVE PAGES", "value_kind": "header"},
        {"normalized_value": "Page Date Rev", "value_kind": "header"},
        {"normalized_value": "25-21-00", "value_kind": "text"},
        {"normalized_value": "01", "value_kind": "numeric"},
        {"normalized_value": "4", "value_kind": "numeric"},
    ]
    template = detect_table_template(rows, cells, values)
    assert template["table_template_type"] == TEMPLATE_LIST_EFFECTIVE_PAGES
    assert "lep_title_hint" in template["table_template_signals"]
