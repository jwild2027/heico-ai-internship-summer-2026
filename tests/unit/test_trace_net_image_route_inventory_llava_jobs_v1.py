from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts/build/visual/build_trace_net_image_route_inventory_llava_jobs_v1.py"
CHECK_SCRIPT = ROOT / "scripts/maintenance/visual/check_trace_net_image_route_inventory_llava_jobs_v1.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def make_source_zip(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("metadata.xml", "<metadata />")
        zf.writestr("00000005.tif", b"fake-tif-5")
        zf.writestr("00000006.tif", b"fake-tif-6")
    return path


def fixture_paths(tmp_path: Path):
    route = write_json(
        tmp_path / "route.json",
        {
            "status": "TRACE_NET_ROUTE_VALIDATOR_RUNNER_BUILT",
            "quality_status": "PASS",
            "route_cards": [
                {
                    "page_id": "p000005",
                    "page_number": 5,
                    "route_label": "image_visual",
                    "source_member": "00000005.tif",
                },
                {
                    "page_id": "p000006",
                    "page_number": 6,
                    "primary_route": "image_or_diagram",
                },
                {
                    "page_id": "p000007",
                    "page_number": 7,
                    "route_label": "normal_text",
                },
            ],
        },
    )
    ocr = write_json(
        tmp_path / "ocr.json",
        {
            "status": "TRACE_NET_OCR_ROUTE_SCAN_PACK_BUILT",
            "quality_status": "PASS",
            "pages": [
                {
                    "page_id": "p000005",
                    "page_number": 5,
                    "source_member": "00000005.tif",
                    "ocr_text": "FIGURE 85 ITEM 1 shows 120-29073-001 near the lateral leg diagram.",
                },
                {
                    "page_id": "p000006",
                    "page_number": 6,
                    "source_member": "00000006.tif",
                    "text": "ILLUS 86 CALLOUT 2. Visual page with labels.",
                },
            ],
        },
    )
    source_zip = make_source_zip(tmp_path / "metadata.zip")
    return route, ocr, source_zip


def test_builder_creates_inventory_jobs_jsonl_csv_and_readme(tmp_path: Path):
    route, ocr, source_zip = fixture_paths(tmp_path)
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--route-validator-runner",
            str(route),
            "--ocr-route-scan-pack",
            str(ocr),
            "--source-package-metadata-zip",
            str(source_zip),
            "--image-visual-summary",
            str(tmp_path / "missing_summary.json"),
            "--output-dir",
            str(out_dir),
            "--llava-output-root",
            "local_data/organization/trace_net/llava_visual_summaries_v1",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    inventory_path = out_dir / "trace_net_image_route_inventory_llava_jobs_v1.json"
    quality_path = out_dir / "trace_net_image_route_inventory_llava_jobs_v1_quality_check.json"
    jobs_path = out_dir / "trace_net_image_route_inventory_llava_jobs_v1_jobs.jsonl"
    csv_path = out_dir / "trace_net_image_route_inventory_llava_jobs_v1_records.csv"
    readme_path = out_dir / "README_trace_net_image_route_inventory_llava_jobs_v1.md"
    for path in [inventory_path, quality_path, jobs_path, csv_path, readme_path]:
        assert path.exists(), path

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert inventory["status"] == "TRACE_NET_IMAGE_ROUTE_INVENTORY_LLAVA_JOBS_BUILT"
    assert inventory["quality_status"] == "PASS"
    assert inventory["summary"]["image_route_record_count"] == 2
    assert inventory["summary"]["llava_job_count"] == 2
    assert inventory["summary"]["missing_llava_summary_count"] == 2
    assert inventory["summary"]["source_trace_ready_count"] == 2
    assert inventory["summary"]["answer_permission_count"] == 0
    assert inventory["summary"]["source_truth_mutation_allowed_count"] == 0
    assert inventory["summary"]["write_attempt_count"] == 0
    assert all(record["answer_permission"] is False for record in inventory["records"])
    assert all("OCR/table/figure-item evidence" in record["authority_note"] for record in inventory["records"])
    assert "120-29073-001" in json.dumps(inventory["records"])

    jobs = [json.loads(line) for line in jobs_path.read_text(encoding="utf-8").splitlines()]
    assert len(jobs) == 2
    assert jobs[0]["llava_status"] == "missing"
    assert "Return structured JSON only" in jobs[0]["recommended_llava_prompt"]
    assert "source_truth_mutation_allowed" in jobs[0]


def test_builder_marks_existing_llava_summary_and_skips_job(tmp_path: Path):
    route, ocr, source_zip = fixture_paths(tmp_path)
    summary = write_json(
        tmp_path / "summary.json",
        {
            "quality_status": "PASS",
            "records": [
                {
                    "page_id": "p000005",
                    "page_number": 5,
                    "visual_summary": "Exploded view with callout labels.",
                }
            ],
        },
    )
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--route-validator-runner",
            str(route),
            "--ocr-route-scan-pack",
            str(ocr),
            "--source-package-metadata-zip",
            str(source_zip),
            "--image-visual-summary",
            str(summary),
            "--output-dir",
            str(out_dir),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    inventory = json.loads((out_dir / "trace_net_image_route_inventory_llava_jobs_v1.json").read_text(encoding="utf-8"))
    assert inventory["summary"]["existing_llava_summary_count"] == 1
    assert inventory["summary"]["missing_llava_summary_count"] == 1
    assert inventory["summary"]["llava_job_count"] == 1
    records_by_page = {record["page_id"]: record for record in inventory["records"]}
    assert records_by_page["p000005"]["llava_status"] == "existing"
    assert records_by_page["p000006"]["llava_status"] == "missing"


def test_quality_checker_passes_required_thresholds(tmp_path: Path):
    route, ocr, source_zip = fixture_paths(tmp_path)
    out_dir = tmp_path / "out"
    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--route-validator-runner",
            str(route),
            "--ocr-route-scan-pack",
            str(ocr),
            "--source-package-metadata-zip",
            str(source_zip),
            "--output-dir",
            str(out_dir),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    inventory_path = out_dir / "trace_net_image_route_inventory_llava_jobs_v1.json"
    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--inventory",
            str(inventory_path),
            "--require-quality-pass",
            "--require-source-route-quality-pass",
            "--require-ocr-scan-pack-quality-pass",
            "--min-image-route-records",
            "1",
            "--min-llava-jobs",
            "1",
            "--min-source-trace-ready",
            "1",
            "--max-unsafe",
            "0",
            "--max-answer-permission",
            "0",
            "--max-source-truth-mutation-allowed",
            "0",
            "--max-write-attempts",
            "0",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "quality_status=PASS" in result.stdout
    assert "llava_job_count=2" in result.stdout


def test_quality_checker_fails_when_inventory_is_tampered(tmp_path: Path):
    inventory = {
        "module_name": "trace_net_image_route_inventory_llava_jobs_v1",
        "status": "TRACE_NET_IMAGE_ROUTE_INVENTORY_LLAVA_JOBS_BUILT",
        "quality_status": "PASS",
        "inputs": {
            "route_validator_runner": {"quality_status": "PASS"},
            "ocr_route_scan_pack": {"quality_status": "PASS"},
        },
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "source_truth_mutation": False,
            "answer_permission": False,
        },
        "summary": {
            "image_route_record_count": 1,
            "llava_job_count": 1,
            "source_trace_ready_count": 1,
            "answer_permission_count": 1,
            "source_truth_mutation_allowed_count": 0,
            "write_attempt_count": 0,
        },
        "artifact_paths": {"inventory": "a", "quality_check": "b", "jobs_jsonl": "c", "records_csv": "d"},
        "records": [{"page_id": "p1", "answer_permission": True, "source_trace_ready": True}],
    }
    path = write_json(tmp_path / "bad_inventory.json", inventory)
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), "--inventory", str(path), "--require-quality-pass"],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    assert "quality_status=FAIL" in result.stdout
    assert "answer_permission_count" in result.stderr


def test_importable_helpers_detect_image_routes_and_figures():
    module = load_module(BUILD_SCRIPT, "image_route_builder")
    assert module.is_image_route_label("image_visual") is True
    assert module.is_image_route_label("normal_text") is False
    candidates = module.infer_figure_candidates("Figure 85 item 1 and part 120-29073-001", {})
    assert {item["candidate_type"] for item in candidates} >= {"figure", "item", "visible_part_number"}
