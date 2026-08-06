import json
from pathlib import Path

from tiff.trace_net_llava_visual_summary_batch_v1 import build_batch, build_arg_parser as batch_parser, parse_json_object
from tiff.trace_net_llava_visual_summary_batch_v1_check import evaluate as eval_batch_check
from tiff.trace_net_visual_callout_table_linker_v1 import build_linker, build_arg_parser as linker_parser, load_evidence_records
from tiff.trace_net_visual_callout_table_linker_v1_check import evaluate as eval_linker_check


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def make_jobs_jsonl(tmp_path: Path) -> Path:
    jobs = [
        {
            "job_id": "llava_visual_summary_job_0001",
            "page_id": "t_p_120_1176_p000361",
            "page_number": 361,
            "source_member": "00000361.tif",
            "route_label": "image",
            "ocr_excerpt_preview": "FIG. 85 ITEM 1 STRUCTURE LATERAL LEG",
            "figure_candidates": [
                {"candidate_type": "figure", "value": "85"},
                {"candidate_type": "item", "value": "1"},
            ],
            "source_trace_ready": True,
            "source_trace_fields": {"page_id": "t_p_120_1176_p000361", "page_number": 361, "source_member": "00000361.tif"},
            "recommended_llava_prompt": "Return JSON only.",
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
    ]
    path = tmp_path / "jobs.jsonl"
    write_jsonl(path, jobs)
    return path


def make_evidence_json(tmp_path: Path) -> Path:
    evidence = {
        "module_name": "fixture_figure_item_evidence",
        "quality_status": "PASS",
        "records": [
            {
                "record_id": "E7",
                "citation_label": "E7",
                "page_id": "t_p_120_1176_p000361",
                "page_number": 361,
                "figure_number": "85",
                "item_number": "1",
                "part_number": "120-29073-001",
                "nomenclature": "STRUCTURE, LATERAL LEG",
                "source_trace_ready": True,
                "citation_ready": True,
            }
        ],
    }
    path = tmp_path / "trusted_evidence.json"
    write_json(path, evidence)
    return path


def test_parse_json_object_strips_fence():
    parsed, status = parse_json_object('```json\n{"page_id":"p1","figure_candidates":["85"]}\n```')
    assert status == "json_direct"
    assert parsed["figure_candidates"] == ["85"]


def test_llava_summary_batch_dry_run_builds_structured_artifact(tmp_path: Path):
    jobs = make_jobs_jsonl(tmp_path)
    args = batch_parser().parse_args([
        "--jobs-jsonl", str(jobs),
        "--output-dir", str(tmp_path / "out"),
        "--llm-mode", "dry_run",
        "--min-llava-summaries", "1",
        "--min-structured-json", "1",
        "--min-source-trace-ready", "1",
    ])
    batch = build_batch(args)
    assert batch["status"] == "TRACE_NET_LLAVA_VISUAL_SUMMARY_BATCH_BUILT"
    assert batch["quality_status"] == "PASS"
    assert batch["summary"]["llava_summary_count"] == 1
    assert batch["summary"]["structured_json_count"] == 1
    assert batch["summary"]["callout_candidate_count"] >= 1
    assert batch["records"][0]["answer_permission"] is False
    assert Path(batch["artifact_paths"]["summaries_jsonl"]).exists()


def test_llava_summary_batch_checker_passes(tmp_path: Path):
    jobs = make_jobs_jsonl(tmp_path)
    args = batch_parser().parse_args(["--jobs-jsonl", str(jobs), "--output-dir", str(tmp_path / "out"), "--llm-mode", "dry_run"])
    batch = build_batch(args)
    check_args = type("Args", (), {
        "require_quality_pass": True,
        "min_llava_summaries": 1,
        "min_structured_json": 1,
        "min_source_trace_ready": 1,
        "max_unsafe": 0,
        "max_answer_permission": 0,
        "max_source_truth_mutation_allowed": 0,
        "max_write_attempts": 0,
    })()
    result = eval_batch_check(batch, check_args)
    assert result["quality_status"] == "PASS"


def test_load_evidence_records_extracts_figure_item_part(tmp_path: Path):
    evidence = make_evidence_json(tmp_path)
    records = load_evidence_records([str(evidence)])
    assert records
    assert "85" in records[0]["figure_candidates"]
    assert "1" in records[0]["callout_candidates"]
    assert "120-29073-001" in records[0]["part_numbers"]


def test_visual_callout_linker_links_llava_observation_to_trusted_evidence(tmp_path: Path):
    jobs = make_jobs_jsonl(tmp_path)
    batch = build_batch(batch_parser().parse_args(["--jobs-jsonl", str(jobs), "--output-dir", str(tmp_path / "batch"), "--llm-mode", "dry_run"]))
    evidence = make_evidence_json(tmp_path)
    args = linker_parser().parse_args([
        "--llava-visual-summary-batch", batch["artifact_paths"]["batch"],
        "--trusted-evidence-artifact", str(evidence),
        "--output-dir", str(tmp_path / "linker"),
        "--min-visual-callout-records", "1",
        "--min-linked-callouts", "1",
        "--min-source-trace-ready", "1",
    ])
    linker = build_linker(args)
    assert linker["status"] == "TRACE_NET_VISUAL_CALLOUT_TABLE_LINKER_BUILT"
    assert linker["quality_status"] == "PASS"
    assert linker["summary"]["linked_callout_record_count"] >= 1
    first = next(r for r in linker["records"] if r["linked"])
    assert first["link_confidence"] == "HIGH"
    assert first["linked_part_number"] == "120-29073-001"
    assert first["answer_permission"] is False


def test_visual_callout_linker_low_when_llava_only(tmp_path: Path):
    visual_batch = {
        "module_name": "trace_net_llava_visual_summary_batch_v1",
        "status": "TRACE_NET_LLAVA_VISUAL_SUMMARY_BATCH_BUILT",
        "quality_status": "PASS",
        "records": [
            {
                "record_id": "llava_visual_summary_0001",
                "page_id": "p1",
                "page_number": 12,
                "figure_candidates": ["99"],
                "callout_candidates": ["3"],
                "visible_text_candidates": ["FIG. 99 ITEM 3"],
                "visual_summary": "Figure 99 with callout 3.",
                "visual_confidence": "medium",
                "source_trace_ready": True,
            }
        ],
    }
    batch_path = tmp_path / "visual_batch.json"
    write_json(batch_path, visual_batch)
    evidence = make_evidence_json(tmp_path)
    args = linker_parser().parse_args([
        "--llava-visual-summary-batch", str(batch_path),
        "--trusted-evidence-artifact", str(evidence),
        "--output-dir", str(tmp_path / "linker"),
        "--min-visual-callout-records", "1",
        "--min-linked-callouts", "0",
    ])
    linker = build_linker(args)
    assert linker["quality_status"] == "PASS"
    assert linker["summary"]["low_confidence_link_count"] == 1
    assert linker["records"][0]["proof_source"] == "none_llava_only"


def test_visual_callout_linker_checker_passes(tmp_path: Path):
    jobs = make_jobs_jsonl(tmp_path)
    batch = build_batch(batch_parser().parse_args(["--jobs-jsonl", str(jobs), "--output-dir", str(tmp_path / "batch"), "--llm-mode", "dry_run"]))
    evidence = make_evidence_json(tmp_path)
    linker = build_linker(linker_parser().parse_args([
        "--llava-visual-summary-batch", batch["artifact_paths"]["batch"],
        "--trusted-evidence-artifact", str(evidence),
        "--output-dir", str(tmp_path / "linker"),
        "--min-linked-callouts", "1",
        "--min-source-trace-ready", "1",
    ]))
    check_args = type("Args", (), {
        "require_quality_pass": True,
        "min_visual_callout_records": 1,
        "min_linked_callouts": 1,
        "min_source_trace_ready": 1,
        "max_unsafe": 0,
        "max_answer_permission": 0,
        "max_source_truth_mutation_allowed": 0,
        "max_write_attempts": 0,
    })()
    result = eval_linker_check(linker, check_args)
    assert result["quality_status"] == "PASS"


def test_b2_table_route_packager_rows_are_synthesized_for_callout_links(tmp_path: Path):
    packager = {
        "quality_status": "PASS",
        "evidence_documents": [
            {
                "evidence_id": "ev_item",
                "page_id": "t_p_120_1176_p000362",
                "table_id": "table_1",
                "row_index": 7,
                "field_name": "ipl_figure_item_or_quantity",
                "normalized_value": "1",
                "source_trace": {"page_id": "t_p_120_1176_p000362", "table_id": "table_1", "field_name": "ipl_figure_item_or_quantity"},
            },
            {
                "evidence_id": "ev_part",
                "page_id": "t_p_120_1176_p000362",
                "table_id": "table_1",
                "row_index": 7,
                "field_name": "covered_part_number",
                "normalized_value": "120-29073-001",
                "source_trace": {"page_id": "t_p_120_1176_p000362", "table_id": "table_1", "field_name": "covered_part_number"},
            },
            {
                "evidence_id": "ev_desc",
                "page_id": "t_p_120_1176_p000362",
                "table_id": "table_1",
                "row_index": 7,
                "field_name": "part_description",
                "normalized_value": "STRUCTURE, LATERAL LEG",
                "source_trace": {"page_id": "t_p_120_1176_p000362", "table_id": "table_1", "field_name": "part_description"},
            },
        ],
    }
    packager_path = tmp_path / "table_route_evidence_packager.json"
    write_json(packager_path, packager)
    records = load_evidence_records([str(packager_path)])
    row_records = [r for r in records if r.get("evidence_shape") == "table_row_group"]
    assert row_records
    assert row_records[0]["callout_candidates"] == ["1"]
    assert row_records[0]["part_numbers"] == ["120-29073-001"]
    assert "STRUCTURE" in row_records[0]["description"]


def test_b2_linker_uses_nearby_unique_table_row_without_llava_only_proof(tmp_path: Path):
    visual_batch = {
        "module_name": "trace_net_llava_visual_summary_batch_v1",
        "status": "TRACE_NET_LLAVA_VISUAL_SUMMARY_BATCH_BUILT",
        "quality_status": "PASS",
        "records": [
            {
                "record_id": "llava_visual_summary_0001",
                "page_id": "t_p_120_1176_p000361",
                "page_number": 361,
                "figure_candidates": [],
                "callout_candidates": ["Item 1"],
                "visible_text_candidates": ["FIG. 85 ITEM 1"],
                "visual_summary": "Figure 85 has callout item 1.",
                "visual_confidence": "medium",
                "source_trace_ready": True,
            }
        ],
    }
    packager = {
        "quality_status": "PASS",
        "evidence_documents": [
            {"page_id": "t_p_120_1176_p000362", "table_id": "table_1", "row_index": 7, "field_name": "ipl_figure_item_or_quantity", "normalized_value": "1", "source_trace": {"page_id": "t_p_120_1176_p000362", "table_id": "table_1"}},
            {"page_id": "t_p_120_1176_p000362", "table_id": "table_1", "row_index": 7, "field_name": "covered_part_number", "normalized_value": "120-29073-001", "source_trace": {"page_id": "t_p_120_1176_p000362", "table_id": "table_1"}},
            {"page_id": "t_p_120_1176_p000362", "table_id": "table_1", "row_index": 7, "field_name": "part_description", "normalized_value": "STRUCTURE, LATERAL LEG", "source_trace": {"page_id": "t_p_120_1176_p000362", "table_id": "table_1"}},
        ],
    }
    batch_path = tmp_path / "visual_batch.json"
    packager_path = tmp_path / "packager.json"
    write_json(batch_path, visual_batch)
    write_json(packager_path, packager)
    args = linker_parser().parse_args([
        "--llava-visual-summary-batch", str(batch_path),
        "--table-route-evidence-packager", str(packager_path),
        "--nearby-page-window", "2",
        "--output-dir", str(tmp_path / "linker"),
        "--min-visual-callout-records", "1",
        "--min-linked-callouts", "1",
        "--min-source-trace-ready", "1",
    ])
    linker = build_linker(args)
    assert linker["quality_status"] == "PASS"
    linked = [r for r in linker["records"] if r.get("linked")]
    assert linked
    assert linked[0]["link_confidence"] == "MEDIUM"
    assert linked[0]["linked_part_number"] == "120-29073-001"
    assert linked[0]["proof_source"] == "trusted_ocr_table_figure_item_evidence"
    assert linked[0]["visual_observation_only"] is True
    assert linked[0]["answer_permission"] is False


def test_b2_visual_candidate_normalization_does_not_split_dict_fragments(tmp_path: Path):
    visual_batch = {
        "module_name": "trace_net_llava_visual_summary_batch_v1",
        "status": "TRACE_NET_LLAVA_VISUAL_SUMMARY_BATCH_BUILT",
        "quality_status": "PASS",
        "records": [
            {
                "record_id": "llava_visual_summary_0001",
                "page_id": "t_p_120_1176_p000017",
                "page_number": 17,
                "figure_candidates": ["{'component': 'device as a whole', 'location': 'center of the image'}"],
                "callout_candidates": ["{'component': 'battery compartment', 'location': 'top left corner'}"],
                "visible_text_candidates": ["TRACE-Net's local visual/page understanding helper"],
                "visual_summary": "A drawing with components but no explicit figure or item number.",
                "visual_confidence": "medium",
                "source_trace_ready": True,
            }
        ],
    }
    batch_path = tmp_path / "visual_batch.json"
    write_json(batch_path, visual_batch)
    args = linker_parser().parse_args([
        "--llava-visual-summary-batch", str(batch_path),
        "--output-dir", str(tmp_path / "linker"),
        "--min-visual-callout-records", "0",
    ])
    linker = build_linker(args)
    assert linker["quality_status"] == "PASS"
    assert linker["summary"]["visual_callout_link_record_count"] == 0
