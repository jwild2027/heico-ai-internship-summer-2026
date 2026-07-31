from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_trace_net_executive_tiff_demo_v5_fast10_deep.py"
V4_SCRIPT = REPO_ROOT / "scripts" / "run_trace_net_executive_tiff_demo_v4.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v5 = load_module(SCRIPT, "trace_net_demo_v5_test")


def make_source_zip(path: Path, start: int = 335, end: int = 352) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for number in range(start, end + 1):
            archive.writestr(f"manual/000000_{number:08d}.tif", f"page-{number}".encode())


def test_v5_is_separate_from_existing_modes() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "run_trace_net_executive_tiff_demo_v5_fast10_deep.py" in str(SCRIPT)
    assert "executive_fast10_deep_v5_" in text
    assert "full_v4_1_demo_modified" in text
    assert "run_trace_net_executive_tiff_demo_v4.py" not in str(SCRIPT)


def test_required_page_count_is_exactly_ten() -> None:
    assert v5.REQUIRED_PAGE_COUNT == 10


def test_default_window_contains_known_evidence_pages() -> None:
    assert v5.DEFAULT_START_PAGE == 339
    assert list(range(v5.DEFAULT_START_PAGE, v5.DEFAULT_START_PAGE + 10)) == list(range(339, 349))
    assert 342 in range(339, 349)
    assert 343 in range(339, 349)
    assert 344 in range(339, 349)


def test_select_page_members_returns_original_pages_339_to_348(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    make_source_zip(source)
    selected = v5.select_page_members(source, 339)
    assert len(selected) == 10
    assert [v5.page_number_from_member(name) for name in selected] == list(range(339, 349))


def test_create_subset_zip_does_not_mutate_source(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    subset = tmp_path / "subset.zip"
    make_source_zip(source)
    before = source.read_bytes()
    manifest = v5.create_subset_zip(source, subset, 339)
    assert source.read_bytes() == before
    assert manifest["page_count"] == 10
    assert manifest["original_source_modified"] is False
    with zipfile.ZipFile(subset) as archive:
        tiffs = [name for name in archive.namelist() if name.endswith(".tif")]
        assert len(tiffs) == 10
        assert "trace_net_fast10_deep_v5_subset_manifest.json" in archive.namelist()


def test_missing_requested_page_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    make_source_zip(source, 339, 347)
    with pytest.raises(ValueError, match="348"):
        v5.select_page_members(source, 339)


def test_stage_plan_has_nine_builds_and_nine_checks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    paths = v5.Fast10Paths(tmp_path / "run")
    plan = v5.build_stage_plan(
        repo=repo,
        paths=paths,
        python_bin="python",
        tesseract_cmd="tesseract",
        psm_modes="3,6,11",
        request_timeout=240,
    )
    assert len(plan) == 18
    assert sum(row.kind == "build" for row in plan) == 9
    assert sum(row.kind == "check" for row in plan) == 9


def test_stage_plan_uses_ten_page_quality_thresholds(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    plan = v5.build_stage_plan(
        repo=repo,
        paths=v5.Fast10Paths(tmp_path / "run"),
        python_bin="python",
        tesseract_cmd="tesseract",
        psm_modes="3,6,11",
        request_timeout=240,
    )
    joined = "\n".join(" ".join(row.command) for row in plan)
    assert "--require-source-page-count 10" in joined
    assert "--min-final-validated 10" in joined
    assert "--max-remaining-unresolved 0" in joined
    assert "--min-lineage-ready 10" in joined
    assert "--min-postgres-contract-ready 10" in joined
    assert "509" not in joined


def test_output_paths_are_v5_specific(tmp_path: Path) -> None:
    paths = v5.Fast10Paths(tmp_path)
    assert "v5" in paths.subset_zip.name
    assert "fast10_deep_v5" in paths.ocr_dir.name
    assert "fast10_deep_v5" in paths.payload_dir.name


def test_parser_defaults_to_fast_evidence_window() -> None:
    args = v5.build_parser().parse_args([])
    assert args.start_page == 339
    assert args.heartbeat_seconds == 5
    assert args.skip_ingestion is False
    assert args.skip_embeddings is False


def test_script_has_no_shell_termination_settings() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "set -e" not in text
    assert "set -u" not in text
    assert "pipefail" not in text
    assert "sys.exit" not in text


def test_corrected_v4_module_is_required() -> None:
    assert V4_SCRIPT.is_file()
    v4 = load_module(V4_SCRIPT, "trace_net_demo_v4_dependency_test")
    assert v4.VERSION == "v4.1"
    assert v4.canonical_operational_route("final nonsense") == "unknown"


def test_classification_gate_rejects_unknown() -> None:
    v4 = load_module(V4_SCRIPT, "trace_net_demo_v4_gate_unknown_test")
    records = [
        v4.PageRecord(f"page_{index:06d}", index, f"{index}.tif", "table", "text", {})
        for index in range(1, 10)
    ]
    records.append(v4.PageRecord("page_000010", 10, "10.tif", "unknown", "", {}))
    gate = v4.classification_gate(records, 10)
    assert gate["quality_status"] == "FAIL"
    assert gate["unclassified_page_count"] == 1


def test_classification_gate_accepts_all_ten_final_routes() -> None:
    v4 = load_module(V4_SCRIPT, "trace_net_demo_v4_gate_pass_test")
    routes = ["table", "table", "plain_text", "image", "table", "plain_text", "table", "image", "blank", "table"]
    records = [
        v4.PageRecord(f"page_{index:06d}", index, f"{index}.tif", route, "text", {})
        for index, route in enumerate(routes, start=1)
    ]
    gate = v4.classification_gate(records, 10)
    assert gate["quality_status"] == "PASS"
    assert gate["classified_page_count"] == 10
    assert gate["unclassified_page_count"] == 0


def test_manifest_safety_contract_is_explicit() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"production_database_writes": False' in text
    assert '"original_source_modified": False' in text
    assert '"full_v4_1_demo_modified": False' in text
