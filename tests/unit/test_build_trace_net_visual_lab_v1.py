from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/build/visual/build_trace_net_visual_lab_v1.py"
VISUAL_LAB = REPO_ROOT / "local_data" / "organization" / "trace_net" / "visual_lab"


def load_module():
    spec = importlib.util.spec_from_file_location("trace_net_visual_lab_builder", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def make_run(root: Path) -> Path:
    run = root / "executive_demo"
    page_ids = [f"t_p_demo_p{i:06d}" for i in range(1, 4)]

    ocr_dir = run / "ocr_route_scan_pack_tesseract_full"
    ocr_records = []
    for index, page_id in enumerate(page_ids, start=1):
        text_path = ocr_dir / "ocr_text" / f"{page_id}.txt"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(f"Page {index} text part 120-29073-00{index}\n", encoding="utf-8")
        ocr_records.append(
            {
                "page_id": page_id,
                "canonical_page_number": index,
                "source_member": f"{index:08d}.tif",
                "source_image_sha256": f"sha{index}",
                "source_image_byte_count": 100 + index,
                "ocr_text_path": str(text_path),
                "ocr_text_sha256": f"ocrsha{index}",
                "ocr_text_char_count": 30,
                "ocr_text_word_count": 5,
                "tesseract_best_psm": 6,
                "tesseract_execution_status": "ok",
                "part_number_tokens": [f"120-29073-00{index}"],
                "accepted_route": "table" if index > 1 else "plain_text",
                "postgres_write_attempt_count": 0,
                "qdrant_write_attempt_count": 0,
                "opensearch_write_attempt_count": 0,
            }
        )
    write_jsonl(ocr_dir / "trace_net_ocr_route_scan_pack_v1_records.jsonl", ocr_records)

    resolver = [
        {"page_id": page_ids[0], "primary_route": "normal_text", "route_confidence": 0.9},
        {"page_id": page_ids[1], "primary_route": "detailed_parts_list", "route_confidence": 0.9},
        {"page_id": page_ids[2], "primary_route": "review_required", "route_confidence": 0.55},
    ]
    write_jsonl(run / "route_confidence_resolver" / "trace_net_route_confidence_resolver_v1_records.jsonl", resolver)
    write_jsonl(
        run / "four_route_operational_resolver" / "trace_net_four_route_operational_resolver_v1_records.jsonl",
        [
            {"page_id": page_ids[0], "operational_route": "plain_text"},
            {"page_id": page_ids[1], "operational_route": "table"},
            {"page_id": page_ids[2], "operational_route": "table"},
        ],
    )
    write_jsonl(
        run / "route_validator_runner" / "trace_net_route_validator_runner_v1_records.jsonl",
        [
            {"page_id": page_ids[0], "validated_operational_route": "plain_text", "validation_status": "PASS"},
            {"page_id": page_ids[1], "validated_operational_route": "table", "validation_status": "PASS"},
            {"page_id": page_ids[2], "validated_operational_route": "table", "validation_status": "GATED"},
        ],
    )
    write_jsonl(
        run / "route_unresolved_retry_probe" / "trace_net_route_unresolved_retry_probe_v1_records.jsonl",
        [
            {"page_id": page_ids[0], "final_validated_operational_route": "plain_text", "retry_status": "not_required"},
            {"page_id": page_ids[1], "final_validated_operational_route": "table", "retry_status": "not_required"},
            {
                "page_id": page_ids[2],
                "source_operational_route": "table",
                "retry_status": "retry_unresolved_validator_gated",
                "final_validation_score": 55,
                "final_validation_reasons": ["no_candidate_probe_met_threshold"],
            },
        ],
    )

    storage_dir = run / "four_route_storage_gate"
    storage_records = [
        {"page_id": page_id, "postgres_write_attempt_count": 0, "qdrant_write_attempt_count": 0, "opensearch_write_attempt_count": 0}
        for page_id in page_ids
    ]
    write_jsonl(storage_dir / "trace_net_four_route_storage_gate_v1_records.jsonl", storage_records)
    write_jsonl(storage_dir / "trace_net_four_route_storage_gate_v1_postgres_graph_manifest.jsonl", [{"page_id": page_id} for page_id in page_ids])
    write_jsonl(storage_dir / "trace_net_four_route_storage_gate_v1_qdrant_candidates.jsonl", [{"page_id": page_id} for page_id in page_ids[:2]])
    write_jsonl(storage_dir / "trace_net_four_route_storage_gate_v1_opensearch_candidates.jsonl", [{"page_id": page_ids[1]}])

    write_jsonl(
        run / "trace_net_demo_graph_nodes_v4.jsonl",
        [
            {"id": page_ids[0], "type": "page", "label": "Page 1"},
            {"id": page_ids[1], "type": "page", "label": "Page 2"},
            {"id": "part:120-29073-002", "type": "part", "label": "120-29073-002"},
        ],
    )
    write_jsonl(
        run / "trace_net_demo_graph_edges_v4.jsonl",
        [{"source": page_ids[1], "target": "part:120-29073-002", "type": "MENTIONS_PART"}],
    )
    write_json(
        run / "trace_net_demo_engram_layers_v4.json",
        {
            "working_memory": {"active_page_count": 3},
            "semantic_memory": {"facts": 1},
            "procedural_memory": {"rules": ["cite"]},
            "episodic_memory": {"run": "demo"},
            "trait_memory": {"style": "direct"},
            "critic_memory": {"checks": ["evidence"]},
        },
    )
    write_jsonl(
        run / "trace_net_demo_page_embeddings_v4.jsonl",
        [
            {"page_id": page_ids[0], "embedding": [1.0, 0.0, 0.2, 0.1], "text_chars": 30},
            {"page_id": page_ids[1], "embedding": [0.9, 0.1, 0.2, 0.0], "text_chars": 30},
        ],
    )
    write_json(
        run / "trace_net_demo_question_01_v4.json",
        {
            "question": "Find part 120-29073-002",
            "exact_identifiers": ["120-29073-002"],
            "selected_route": "part_number",
            "evidence_records": [{"id": "E1", "page_id": page_ids[1], "route": "table", "score": 100}],
            "gemma_status": "PASS",
            "final_answer": "Part 120-29073-002 appears on page 2 (E1).",
            "validation": {"empty_answer_check": "PASS", "invalid_citation_labels": []},
            "final_release_decision": "PASS",
        },
    )
    return run


def test_visual_lab_static_site_files_exist():
    expected = [
        "index.html",
        "01_source_lineage_explorer.html",
        "02_ocr_explorer.html",
        "03_page_classifier_explorer.html",
        "04_graph_explorer.html",
        "05_vector_explorer.html",
        "06_engram_explorer.html",
        "07_storage_explorer.html",
        "08_retrieval_trace_explorer.html",
        "09_answer_validation_explorer.html",
        "assets/trace_net_visual_lab.css",
        "assets/trace_net_visual_lab.js",
        "data/catalog.json",
    ]
    for relative in expected:
        assert (VISUAL_LAB / relative).is_file(), relative


def test_exporter_builds_browser_safe_dataset(tmp_path: Path):
    module = load_module()
    run = make_run(tmp_path)
    site = tmp_path / "visual_lab"
    args = module.build_parser().parse_args(
        [
            "--run-dir", str(run),
            "--visual-lab-dir", str(site),
            "--dataset-slug", "mini_3",
            "--dataset-label", "Mini 3-page run",
            "--require-page-count", "3",
            "--quality",
        ]
    )
    manifest = module.build_export(args)
    assert manifest["quality_status"] == "PASS"
    assert manifest["page_count"] == 3
    assert manifest["route_counts"] == {"plain_text": 1, "table": 2}
    assert manifest["graph_node_count"] == 3
    assert manifest["graph_edge_count"] == 1
    assert manifest["embedding_point_count"] == 2
    assert manifest["embedding_dimension"] == 4
    assert manifest["engram_layer_count"] == 6
    assert manifest["question_count"] == 1
    assert manifest["graph_only_safety_hold_count"] == 1
    assert manifest["production_write_attempt_count"] == 0


def test_exported_projection_is_two_dimensional(tmp_path: Path):
    module = load_module()
    run = make_run(tmp_path)
    site = tmp_path / "visual_lab"
    args = module.build_parser().parse_args([
        "--run-dir", str(run), "--visual-lab-dir", str(site),
        "--dataset-slug", "mini_3", "--dataset-label", "Mini", "--quality",
    ])
    module.build_export(args)
    payload = json.loads((site / "data" / "mini_3" / "vector_projection.json").read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "PASS"
    assert payload["summary"]["dimension"] == 4
    assert len(payload["records"]) == 2
    assert all(isinstance(record["x"], float) and isinstance(record["y"], float) for record in payload["records"])


def test_graph_only_page_remains_visible_but_not_vector_eligible(tmp_path: Path):
    module = load_module()
    run = make_run(tmp_path)
    site = tmp_path / "visual_lab"
    args = module.build_parser().parse_args([
        "--run-dir", str(run), "--visual-lab-dir", str(site),
        "--dataset-slug", "mini_3", "--dataset-label", "Mini", "--quality",
    ])
    module.build_export(args)
    classification = json.loads((site / "data" / "mini_3" / "classification.json").read_text(encoding="utf-8"))["records"]
    storage = json.loads((site / "data" / "mini_3" / "storage_plan.json").read_text(encoding="utf-8"))["records"]
    held = next(record for record in classification if record["page_number"] == 3)
    held_storage = next(record for record in storage if record["page_number"] == 3)
    assert held["final_route"] == "table"
    assert held["graph_only_safety_hold"] is True
    assert held_storage["graph_ready"] is True
    assert held_storage["vector_eligible"] is False
    assert held_storage["exact_search_eligible"] is False


def test_catalog_registers_dataset(tmp_path: Path):
    module = load_module()
    run = make_run(tmp_path)
    site = tmp_path / "visual_lab"
    args = module.build_parser().parse_args([
        "--run-dir", str(run), "--visual-lab-dir", str(site),
        "--dataset-slug", "mini_3", "--dataset-label", "Mini", "--quality",
    ])
    module.build_export(args)
    catalog = json.loads((site / "data" / "catalog.json").read_text(encoding="utf-8"))
    assert len(catalog["datasets"]) == 1
    assert catalog["datasets"][0]["slug"] == "mini_3"
    assert catalog["datasets"][0]["quality_status"] == "PASS"
