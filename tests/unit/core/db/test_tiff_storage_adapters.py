from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiff.storage_adapters import (
    LocalArtifactCatalogStore,
    LocalArtifactPaths,
    LocalJsonlFeedbackStore,
    OpenSearchKeywordStore,
    PostgresCatalogStore,
    QdrantVectorStore,
    adapter_readiness,
    build_local_store_bundle,
)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_local_artifacts(tmp_path: Path) -> LocalArtifactPaths:
    export = tmp_path / "local_data" / "organization" / "export"
    graph = tmp_path / "local_data" / "organization" / "graph"
    _write_json(export / "organization_summary.json", {"manuals": 1, "pages": 1, "parts": 1})
    _write_json(
        export / "part_tree.json",
        {
            "parts": [
                {
                    "part_number": "120-37313-001",
                    "nomenclature": "HOLDER, MAGAZINE",
                    "pages": [{"page_id": "p1"}],
                }
            ]
        },
    )
    _write_json(
        export / "page_index.json",
        {
            "pages": [
                {
                    "page_id": "t_p_120_1176_p000083",
                    "source_url": "http://localhost/source/83",
                    "tiff_path": "pages/000083.tif",
                    "ocr_text_path": "ocr/000083.txt",
                }
            ]
        },
    )
    _write_json(export / "ata_tree.json", {"ata_sections": [{"ata_code": "25-21-00", "pages": ["p1"]}]})
    _write_json(tmp_path / "local_data" / "pipeline_runs" / "latest_quality_gate.json", {"status": "ok"})
    _write_json(graph / "graph_quality.json", {"status": "ok", "page_context_nodes": 1})
    return LocalArtifactPaths(repo_root=tmp_path)


def test_local_catalog_store_reads_part_page_ata_and_summary(tmp_path: Path) -> None:
    paths = make_local_artifacts(tmp_path)
    store = LocalArtifactCatalogStore(paths)

    assert store.organization_summary()["status"] == "ok"
    assert store.get_part("120-37313-001")["nomenclature"] == "HOLDER, MAGAZINE"
    assert store.get_part("12037313001")["nomenclature"] == "HOLDER, MAGAZINE"
    assert store.get_page("t_p_120_1176_p000083")["source_url"] == "http://localhost/source/83"
    assert store.get_ata("25-21-00")["ata_code"] == "25-21-00"
    assert store.get_part("NO-SUCH-PART") is None


def test_feedback_store_writes_jsonl_and_summary(tmp_path: Path) -> None:
    paths = make_local_artifacts(tmp_path)
    store = LocalJsonlFeedbackStore(paths)

    result = store.submit_feedback({"question": "q", "rating": "up", "category": "useful", "reason": "ok"})

    assert result["status"] == "ok"
    summary = store.feedback_summary()
    assert summary["total"] == 1
    assert summary["by_rating"]["up"] == 1
    assert summary["by_category"]["useful"] == 1


def test_adapter_readiness_for_local_bundle(tmp_path: Path) -> None:
    make_local_artifacts(tmp_path)
    bundle = build_local_store_bundle(repo_root=tmp_path)

    report = adapter_readiness(bundle)

    assert report["status"] == "ok"
    assert report["mode"] == "local_artifacts"
    assert report["part_probe"]["found"] is True
    assert report["page_probe"]["found"] is True


def test_production_placeholders_raise_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        PostgresCatalogStore("postgresql://example").organization_summary()
    with pytest.raises(NotImplementedError):
        OpenSearchKeywordStore("http://localhost:9200", "ocr").search("test")
    with pytest.raises(NotImplementedError):
        QdrantVectorStore("http://localhost:6333", "chunks").search("test")
