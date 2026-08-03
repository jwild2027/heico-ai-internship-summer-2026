"""Production storage adapter stubs for the TIFF/GraphRAG backend.

These classes intentionally do not connect to PostgreSQL, OpenSearch, Qdrant,
or ResCarta yet. They define the stable interfaces and readiness checks that
will be implemented after production services are available.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
import json
import os

DEFAULT_SCHEMA_DIR = Path("local_data/architecture/production_schema")
DEFAULT_OUTPUT = Path("local_data/api/production_adapter_stubs_ready.json")


class ProductionAdapterNotConfigured(RuntimeError):
    """Raised when a production adapter method is called before configuration."""


@dataclass(frozen=True)
class ProductionAdapterConfig:
    """Connection/configuration placeholders for future production services."""

    postgres_dsn: Optional[str] = None
    opensearch_url: Optional[str] = None
    qdrant_url: Optional[str] = None
    rescarta_base_url: Optional[str] = None
    schema_dir: str = str(DEFAULT_SCHEMA_DIR)

    @classmethod
    def from_env(cls, *, schema_dir: str | Path = DEFAULT_SCHEMA_DIR) -> "ProductionAdapterConfig":
        return cls(
            postgres_dsn=os.getenv("HEICO_POSTGRES_DSN") or os.getenv("DATABASE_URL"),
            opensearch_url=os.getenv("HEICO_OPENSEARCH_URL"),
            qdrant_url=os.getenv("HEICO_QDRANT_URL"),
            rescarta_base_url=os.getenv("HEICO_RESCARTA_BASE_URL"),
            schema_dir=str(schema_dir),
        )


@dataclass(frozen=True)
class AdapterReadinessCheck:
    name: str
    ok: bool
    message: str


@dataclass(frozen=True)
class ProductionAdapterReadiness:
    status: str
    mode: str
    schema_dir: str
    postgres_configured: bool
    opensearch_configured: bool
    qdrant_configured: bool
    rescarta_configured: bool
    schema_artifacts_present: bool
    checks: List[AdapterReadinessCheck]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["checks"] = [asdict(check) for check in self.checks]
        return data


class ProductionAdapterBase:
    service_name = "production_service"
    config_key = ""

    def __init__(self, config: ProductionAdapterConfig | None = None) -> None:
        self.config = config or ProductionAdapterConfig.from_env()

    @property
    def configured(self) -> bool:
        if not self.config_key:
            return False
        return bool(getattr(self.config, self.config_key, None))

    def readiness_check(self) -> AdapterReadinessCheck:
        if self.configured:
            return AdapterReadinessCheck(
                name=f"{self.service_name}_configured",
                ok=True,
                message=f"{self.service_name} configuration is present.",
            )
        return AdapterReadinessCheck(
            name=f"{self.service_name}_configured",
            ok=False,
            message=(
                f"{self.service_name} is not configured yet. This is expected before "
                "production services are available."
            ),
        )

    def _not_configured(self, method_name: str) -> None:
        raise ProductionAdapterNotConfigured(
            f"{self.__class__.__name__}.{method_name} is a production stub. "
            "Configure the production service and implement the adapter before use."
        )


class PostgresCatalogStore(ProductionAdapterBase):
    """Future PostgreSQL implementation for documents/pages/parts/catalog graph."""

    service_name = "postgres"
    config_key = "postgres_dsn"

    def get_part(self, part_number: str) -> Mapping[str, Any]:
        self._not_configured("get_part")

    def get_page(self, page_id: str) -> Mapping[str, Any]:
        self._not_configured("get_page")

    def get_ata(self, ata_code: str) -> Mapping[str, Any]:
        self._not_configured("get_ata")

    def organization_summary(self) -> Mapping[str, Any]:
        self._not_configured("organization_summary")


class PostgresTraceStore(ProductionAdapterBase):
    """Future PostgreSQL implementation for graph trace traversal."""

    service_name = "postgres_trace"
    config_key = "postgres_dsn"

    def trace_part(self, part_number: str) -> Mapping[str, Any]:
        self._not_configured("trace_part")

    def trace_page(self, page_id: str) -> Mapping[str, Any]:
        self._not_configured("trace_page")

    def trace_vector_payload(self, *, page_id: str, chunk_id: str | None = None, score: float | None = None) -> Mapping[str, Any]:
        self._not_configured("trace_vector_payload")


class PostgresFeedbackStore(ProductionAdapterBase):
    """Future PostgreSQL implementation for feedback/QA/eval candidate capture."""

    service_name = "postgres_feedback"
    config_key = "postgres_dsn"

    def save_feedback(self, feedback: Mapping[str, Any]) -> Mapping[str, Any]:
        self._not_configured("save_feedback")

    def feedback_summary(self) -> Mapping[str, Any]:
        self._not_configured("feedback_summary")


class PostgresQualityStore(ProductionAdapterBase):
    """Future PostgreSQL implementation for quality/pipeline status records."""

    service_name = "postgres_quality"
    config_key = "postgres_dsn"

    def status(self) -> Mapping[str, Any]:
        self._not_configured("status")


class OpenSearchKeywordSearchStore(ProductionAdapterBase):
    """Future OpenSearch implementation for OCR/chunk/context/part text search."""

    service_name = "opensearch"
    config_key = "opensearch_url"

    def search_pages(self, query: str, *, limit: int = 10) -> List[Mapping[str, Any]]:
        self._not_configured("search_pages")

    def search_chunks(self, query: str, *, limit: int = 10) -> List[Mapping[str, Any]]:
        self._not_configured("search_chunks")

    def search_parts(self, query: str, *, limit: int = 10) -> List[Mapping[str, Any]]:
        self._not_configured("search_parts")


class QdrantVectorStore(ProductionAdapterBase):
    """Future Qdrant implementation for vector retrieval.

    Expected payload invariant:
        every result must include at least page_id and chunk_id so PostgreSQL
        graph traversal can resolve document/source/context evidence.
    """

    service_name = "qdrant"
    config_key = "qdrant_url"

    def search_chunks(self, query_vector: List[float], *, limit: int = 10) -> List[Mapping[str, Any]]:
        self._not_configured("search_chunks")

    def search_page_contexts(self, query_vector: List[float], *, limit: int = 10) -> List[Mapping[str, Any]]:
        self._not_configured("search_page_contexts")


class ResCartaSourceStore(ProductionAdapterBase):
    """Future resolver for real ResCarta/source deep links."""

    service_name = "rescarta"
    config_key = "rescarta_base_url"

    def source_for_page(self, page_id: str) -> Mapping[str, Any]:
        self._not_configured("source_for_page")

    def build_deep_link(self, *, document_id: str, page_number: int | str) -> str:
        self._not_configured("build_deep_link")


def schema_artifact_paths(schema_dir: str | Path = DEFAULT_SCHEMA_DIR) -> Dict[str, Path]:
    base = Path(schema_dir)
    return {
        "postgres_schema": base / "postgres_schema.sql",
        "opensearch_mappings": base / "opensearch_mappings.json",
        "qdrant_collections": base / "qdrant_collections.json",
        "migration_plan": base / "storage_migration_plan.md",
        "summary": base / "production_schema_summary.json",
    }


def schema_artifacts_present(schema_dir: str | Path = DEFAULT_SCHEMA_DIR) -> bool:
    return all(path.exists() for path in schema_artifact_paths(schema_dir).values())


def build_production_adapter_readiness(
    config: ProductionAdapterConfig | None = None,
    *,
    require_configured: bool = False,
) -> ProductionAdapterReadiness:
    cfg = config or ProductionAdapterConfig.from_env()
    adapters = [
        PostgresCatalogStore(cfg),
        OpenSearchKeywordSearchStore(cfg),
        QdrantVectorStore(cfg),
        ResCartaSourceStore(cfg),
    ]
    checks = [adapter.readiness_check() for adapter in adapters]

    artifacts_present = schema_artifacts_present(cfg.schema_dir)
    checks.append(
        AdapterReadinessCheck(
            name="production_schema_artifacts_present",
            ok=artifacts_present,
            message=(
                "Production schema artifacts are present."
                if artifacts_present
                else f"Production schema artifacts are missing under {cfg.schema_dir}."
            ),
        )
    )

    configured_flags = [adapter.configured for adapter in adapters]
    if require_configured:
        status_ok = artifacts_present and all(configured_flags)
    else:
        # Before server access, stubs are allowed to be unconfigured. Schema
        # artifacts are the important readiness signal.
        status_ok = artifacts_present

    return ProductionAdapterReadiness(
        status="OK" if status_ok else "NEEDS ATTENTION",
        mode="production_stubs",
        schema_dir=cfg.schema_dir,
        postgres_configured=bool(cfg.postgres_dsn),
        opensearch_configured=bool(cfg.opensearch_url),
        qdrant_configured=bool(cfg.qdrant_url),
        rescarta_configured=bool(cfg.rescarta_base_url),
        schema_artifacts_present=artifacts_present,
        checks=checks,
    )


def write_production_adapter_readiness(
    output: str | Path = DEFAULT_OUTPUT,
    *,
    config: ProductionAdapterConfig | None = None,
    require_configured: bool = False,
) -> ProductionAdapterReadiness:
    readiness = build_production_adapter_readiness(config, require_configured=require_configured)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(readiness.to_dict(), indent=2), encoding="utf-8")
    return readiness


__all__ = [
    "AdapterReadinessCheck",
    "DEFAULT_OUTPUT",
    "DEFAULT_SCHEMA_DIR",
    "OpenSearchKeywordSearchStore",
    "PostgresCatalogStore",
    "PostgresFeedbackStore",
    "PostgresQualityStore",
    "PostgresTraceStore",
    "ProductionAdapterConfig",
    "ProductionAdapterNotConfigured",
    "ProductionAdapterReadiness",
    "QdrantVectorStore",
    "ResCartaSourceStore",
    "build_production_adapter_readiness",
    "schema_artifact_paths",
    "schema_artifacts_present",
    "write_production_adapter_readiness",
]
