from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/operations/ingestion/run_trace_net_executive_tiff_demo_v5_fast10_deep.py"
V4_SCRIPT = REPO_ROOT / "scripts/operations/validation/run_trace_net_executive_tiff_demo_v4.py"


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
    assert v5.VERSION == "v5.1"
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
    assert "--quality" in joined
    assert "--min-final-validated 9" in joined
    assert "--max-remaining-unresolved 1" in joined
    assert "--min-lineage-ready 10" in joined
    assert "--min-postgres-contract-ready 10" in joined
    assert "509" not in joined


def _write_ingestion_reports(paths: v5.Fast10Paths, *, final_validated: int, remaining: int) -> None:
    payloads = {
        "ocr": {"quality_status": "PASS", "summary": {"route_record_count": 10}},
        "resolver": {"quality_status": "PASS", "summary": {}},
        "four_route": {"quality_status": "PASS", "summary": {}},
        "validator": {"quality_status": "PASS", "summary": {}},
        "retry": {
            "quality_status": "PASS",
            "summary": {
                "final_validated_route_count": final_validated,
                "remaining_validator_gated_unresolved_count": remaining,
                "final_validated_route_counts": {"plain_text": 4, "table": final_validated - 4},
            },
        },
        "storage": {
            "quality_status": "PASS",
            "summary": {
                "postgres_graph_record_count": 10,
                "invalid_operational_route_count": 0,
                "final_validated_route_counts": {"plain_text": 4, "table": 6},
                "qdrant_embedding_allowed_count": final_validated,
                "opensearch_index_allowed_count": 5,
            },
        },
        "loader": {"quality_status": "PASS", "summary": {}},
        "contract": {
            "quality_status": "PASS",
            "summary": {"lineage_ready_count": 10, "missing_lineage_count": 0},
        },
        "retrieval_payload_audit": {
            "quality_status": "PASS",
            "summary": {"qdrant_payload_count": final_validated, "opensearch_payload_count": 5},
        },
    }
    for stage, payload in payloads.items():
        v5.write_json(paths.reports[stage], payload)


def _successful_stage_results(paths: v5.Fast10Paths):
    return [
        (v5.StageCommand(stage, kind, [], report), v5.StageResult(0, 0.0, report))
        for stage, report in paths.reports.items()
        for kind in ("build", "check")
    ]


def test_ingestion_summary_accepts_one_safe_graph_only_hold(tmp_path: Path) -> None:
    paths = v5.Fast10Paths(tmp_path / "run")
    _write_ingestion_reports(paths, final_validated=9, remaining=1)
    summary = v5.build_ingestion_summary(paths, _successful_stage_results(paths))
    assert summary["quality_status"] == "PASS"
    assert summary["fully_validated_route_count"] == 9
    assert summary["validator_gated_graph_only_count"] == 1
    assert summary["safely_routed_page_count"] == 10
    assert summary["final_validated_route_counts"] == {"plain_text": 4, "table": 6}


def test_ingestion_summary_rejects_more_than_one_graph_only_hold(tmp_path: Path) -> None:
    paths = v5.Fast10Paths(tmp_path / "run")
    _write_ingestion_reports(paths, final_validated=8, remaining=2)
    summary = v5.build_ingestion_summary(paths, _successful_stage_results(paths))
    assert summary["quality_status"] == "FAIL"
    assert any("more than one page" in failure for failure in summary["failures"])


def test_validator_gated_page_ids_uses_storage_policy() -> None:
    payload = {
        "records": [
            {"page_id": "page_1", "validator_gated": False, "storage_decision": "validated_graph_and_semantic_index"},
            {"page_id": "page_2", "validator_gated": True, "storage_decision": "graph_only_validator_gated"},
        ]
    }
    assert v5.validator_gated_page_ids(payload) == {"page_2"}


def test_v5_embeddings_skip_validator_gated_page(tmp_path: Path) -> None:
    v4 = load_module(V4_SCRIPT, "trace_net_demo_v4_embedding_hold_test")
    records = [
        v4.PageRecord("page_1", 1, "1.tif", "table", "searchable table text", {}),
        v4.PageRecord("page_2", 2, "2.tif", "table", "held table text", {}),
    ]
    original_embed_text = v4.embed_text
    try:
        v4.embed_text = lambda *args, **kwargs: [1.0, 2.0, 3.0]
        results = v5.build_v5_embeddings(
            v4, tmp_path, records, {"page_2"}, "http://127.0.0.1:11434", "bge-m3:latest", 10, 1000
        )
    finally:
        v4.embed_text = original_embed_text
    assert results[0].status == "PASS"
    assert results[1].status == "SKIP_VALIDATOR_GATED"
    summary = json.loads((tmp_path / "trace_net_demo_embedding_summary_v4.json").read_text())
    assert summary["embedded_count"] == 1
    assert summary["validator_gated_skip_count"] == 1


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
