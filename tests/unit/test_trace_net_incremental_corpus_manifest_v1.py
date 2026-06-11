import json
from pathlib import Path

from tiff.trace_net_incremental_corpus_manifest_v1 import (
    build_incremental_corpus_manifest,
    page_id_from_path,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_page_id_from_path_extracts_six_digit_page() -> None:
    assert page_id_from_path("sample/t_p_120_1176_p000003.tif") == "t_p_120_1176_p000003"
    assert page_id_from_path("sample/page_000004.tiff") == "t_p_120_1176_p000004"


def test_build_manifest_detects_new_changed_and_page_dirty_stages(tmp_path: Path) -> None:
    source_root = tmp_path / "sample_tiffs"
    source_root.mkdir()
    p1 = source_root / "t_p_120_1176_p000001.tif"
    p2 = source_root / "t_p_120_1176_p000002.tif"
    p1.write_text("same", encoding="utf-8")
    p2.write_text("changed", encoding="utf-8")

    page_registry = tmp_path / "page_registry.json"
    write_json(page_registry, {
        "quality_status": "PASS",
        "records": [
            {"page_id": "t_p_120_1176_p000001", "page_number": 1, "detected_elements": [{}], "recommended_extraction_routes": ["source_text_route"]},
            {"page_id": "t_p_120_1176_p000002", "page_number": 2, "detected_elements": [{}], "recommended_extraction_routes": ["source_text_route"]},
        ],
    })
    candidates = tmp_path / "candidates.json"
    write_json(candidates, {
        "quality_status": "PASS",
        "records": [
            {"page_id": "t_p_120_1176_p000001", "rag_bucket": "source_text_evidence"},
            {"page_id": "t_p_120_1176_p000002", "rag_bucket": "source_text_evidence"},
        ],
    })
    previous = tmp_path / "previous.json"
    # p1 old fingerprint matches, p2 old fingerprint differs.
    write_json(previous, {
        "source_file_records": [
            {"source_path": str(p1).replace("\\", "/"), "fingerprint": f"stat:{p1.stat().st_size}:{p1.stat().st_mtime_ns}", "page_ids": ["t_p_120_1176_p000001"]},
            {"source_path": str(p2).replace("\\", "/"), "fingerprint": "stat:0:0", "page_ids": ["t_p_120_1176_p000002"]},
        ]
    })

    manifest = build_incremental_corpus_manifest(
        page_registry_path=page_registry,
        embedding_candidates_path=candidates,
        previous_manifest_path=previous,
        source_roots=[source_root],
        output_dir=tmp_path / "out",
        require_page_count=2,
        min_source_records=2,
        write_quality=True,
    )

    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["source_record_count"] == 2
    assert manifest["summary"]["unchanged_source_count"] == 1
    assert manifest["summary"]["changed_source_count"] == 1
    assert manifest["summary"]["dirty_page_count"] == 1
    dirty = [r for r in manifest["page_manifest_records"] if r["dirty_stage_count"] > 0]
    assert dirty[0]["page_id"] == "t_p_120_1176_p000002"
    assert "qdrant_upsert" in dirty[0]["dirty_stages"]
    assert "opensearch_upsert" in dirty[0]["dirty_stages"]


def test_manifest_is_read_only_and_not_answer_authority(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "t_p_120_1176_p000001.tif").write_text("x", encoding="utf-8")
    page_registry = tmp_path / "page_registry.json"
    write_json(page_registry, {"records": [{"page_id": "t_p_120_1176_p000001"}]})

    manifest = build_incremental_corpus_manifest(
        page_registry_path=page_registry,
        source_roots=[source_root],
        output_dir=tmp_path / "out",
        require_page_count=1,
    )

    assert manifest["writeback_mode"] == "read_only_manifest"
    assert manifest["can_answer_directly"] is False
    assert manifest["can_prove_claims"] is False
    assert manifest["can_mutate_source_truth"] is False
    assert manifest["summary"]["source_truth_mutation_allowed_count"] == 0
