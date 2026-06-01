from __future__ import annotations

from pathlib import Path

import pytest

from tiff.production_adapters import (
    OpenSearchKeywordSearchStore,
    PostgresCatalogStore,
    ProductionAdapterConfig,
    ProductionAdapterNotConfigured,
    QdrantVectorStore,
    ResCartaSourceStore,
    build_production_adapter_readiness,
    schema_artifact_paths,
    schema_artifacts_present,
    write_production_adapter_readiness,
)


def _write_schema_artifacts(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    for path in schema_artifact_paths(base).values():
        if path.suffix == ".json":
            path.write_text("{}", encoding="utf-8")
        else:
            path.write_text("draft", encoding="utf-8")


def test_schema_artifact_detection(tmp_path: Path) -> None:
    assert not schema_artifacts_present(tmp_path / "schema")
    _write_schema_artifacts(tmp_path / "schema")
    assert schema_artifacts_present(tmp_path / "schema")


def test_readiness_allows_unconfigured_stubs_when_schema_exists(tmp_path: Path) -> None:
    schema_dir = tmp_path / "schema"
    _write_schema_artifacts(schema_dir)
    readiness = build_production_adapter_readiness(ProductionAdapterConfig(schema_dir=str(schema_dir)))
    assert readiness.status == "OK"
    assert readiness.mode == "production_stubs"
    assert readiness.schema_artifacts_present is True
    assert readiness.postgres_configured is False


def test_readiness_can_require_service_configuration(tmp_path: Path) -> None:
    schema_dir = tmp_path / "schema"
    _write_schema_artifacts(schema_dir)
    readiness = build_production_adapter_readiness(
        ProductionAdapterConfig(schema_dir=str(schema_dir)),
        require_configured=True,
    )
    assert readiness.status == "NEEDS ATTENTION"


def test_stub_methods_raise_clear_not_configured_error() -> None:
    config = ProductionAdapterConfig()
    with pytest.raises(ProductionAdapterNotConfigured):
        PostgresCatalogStore(config).get_part("120-37313-001")
    with pytest.raises(ProductionAdapterNotConfigured):
        OpenSearchKeywordSearchStore(config).search_pages("magazine holder")
    with pytest.raises(ProductionAdapterNotConfigured):
        QdrantVectorStore(config).search_chunks([0.1, 0.2])
    with pytest.raises(ProductionAdapterNotConfigured):
        ResCartaSourceStore(config).source_for_page("p1")


def test_write_readiness_json(tmp_path: Path) -> None:
    schema_dir = tmp_path / "schema"
    _write_schema_artifacts(schema_dir)
    output = tmp_path / "ready.json"
    readiness = write_production_adapter_readiness(output, config=ProductionAdapterConfig(schema_dir=str(schema_dir)))
    assert output.exists()
    assert readiness.status == "OK"
    assert '"mode": "production_stubs"' in output.read_text(encoding="utf-8")
