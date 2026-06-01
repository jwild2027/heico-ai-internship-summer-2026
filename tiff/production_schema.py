"""Production storage schema drafts for the TIFF technical-library backend.

These drafts are intentionally implementation-neutral. They do not connect to
PostgreSQL, OpenSearch, or Qdrant; they generate versioned schema artifacts that
we can review before the production migration.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any, Dict, Iterable, List, Mapping, Sequence

SCHEMA_VERSION = "tiff_storage_schema_v0_1"
DEFAULT_OUTPUT_DIR = Path("local_data/architecture/production_schema")


@dataclass(frozen=True)
class SchemaArtifact:
    """A generated schema artifact."""

    relative_path: str
    content: str
    description: str


@dataclass(frozen=True)
class SchemaDraftSummary:
    """Summary of generated production schema drafts."""

    status: str
    schema_version: str
    output_dir: str
    artifacts_written: int
    postgres_tables: List[str]
    opensearch_indices: List[str]
    qdrant_collections: List[str]
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


POSTGRES_TABLES: Sequence[str] = (
    "documents",
    "ata_sections",
    "pages",
    "source_files",
    "source_links",
    "ocr_records",
    "parts",
    "nomenclature",
    "part_mentions",
    "page_contexts",
    "topics",
    "page_context_topics",
    "rag_chunks",
    "rag_retrieval_events",
    "user_questions",
    "answers",
    "answer_sources",
    "user_feedback",
    "qa_findings",
    "file_state",
    "pipeline_runs",
    "quality_snapshots",
)

OPENSEARCH_INDICES: Sequence[str] = (
    "tiff_pages_v1",
    "tiff_rag_chunks_v1",
    "tiff_page_contexts_v1",
    "tiff_parts_v1",
)

QDRANT_COLLECTIONS: Sequence[str] = (
    "tiff_rag_chunks_v1",
    "tiff_page_contexts_v1",
    "tiff_image_pages_v1_future",
)


def postgres_schema_sql() -> str:
    """Return PostgreSQL DDL draft.

    Notes:
    - TIFF/PDF bytes are not stored in PostgreSQL.
    - Raw source files remain in ResCarta/file storage.
    - PostgreSQL owns metadata, relationships, quality, feedback, and traceability.
    - Qdrant owns dense vectors.
    - OpenSearch owns keyword/search indexes.
    """

    return """-- TIFF technical-library production schema draft
-- Version: tiff_storage_schema_v0_1
-- Purpose: metadata, graph relationships, source traceability, feedback, and quality state.
-- Raw TIFF bytes stay in file storage/ResCarta. Dense vectors stay in Qdrant.

CREATE SCHEMA IF NOT EXISTS tiff_lib;

CREATE TABLE IF NOT EXISTS tiff_lib.documents (
    document_id TEXT PRIMARY KEY,
    manual_title TEXT NOT NULL,
    manual_number TEXT,
    source_package_id TEXT,
    source_package_uri TEXT,
    document_type TEXT DEFAULT 'technical_manual',
    revision TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.ata_sections (
    ata_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES tiff_lib.documents(document_id) ON DELETE CASCADE,
    ata_code TEXT NOT NULL,
    title TEXT,
    page_count INTEGER DEFAULT 0,
    part_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE (document_id, ata_code)
);

CREATE TABLE IF NOT EXISTS tiff_lib.pages (
    page_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES tiff_lib.documents(document_id) ON DELETE CASCADE,
    ata_id TEXT REFERENCES tiff_lib.ata_sections(ata_id) ON DELETE SET NULL,
    page_number INTEGER,
    page_label TEXT,
    page_role TEXT,
    source_package_page_number INTEGER,
    source_image_path TEXT,
    source_image_uri TEXT,
    ocr_text_path TEXT,
    ocr_text_uri TEXT,
    ocr_hash TEXT,
    image_hash TEXT,
    visible_text_chars INTEGER DEFAULT 0,
    has_empty_ocr BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.source_files (
    source_file_id TEXT PRIMARY KEY,
    page_id TEXT REFERENCES tiff_lib.pages(page_id) ON DELETE CASCADE,
    document_id TEXT REFERENCES tiff_lib.documents(document_id) ON DELETE CASCADE,
    file_type TEXT NOT NULL, -- tiff, ocr_text, metadata_xml, other
    path TEXT NOT NULL,
    uri TEXT,
    byte_size BIGINT,
    modified_at TIMESTAMPTZ,
    content_hash TEXT,
    source_package_id TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.source_links (
    source_link_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES tiff_lib.pages(page_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES tiff_lib.documents(document_id) ON DELETE CASCADE,
    rescarta_url TEXT,
    source_url TEXT,
    tiff_uri TEXT,
    ocr_uri TEXT,
    link_status TEXT DEFAULT 'local_ready', -- local_ready, real_rescarta_ready, broken, pending
    is_placeholder BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE (page_id)
);

CREATE TABLE IF NOT EXISTS tiff_lib.ocr_records (
    ocr_record_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES tiff_lib.pages(page_id) ON DELETE CASCADE,
    engine TEXT,
    engine_version TEXT,
    language TEXT DEFAULT 'eng',
    ocr_status TEXT NOT NULL, -- missing, header_only, full_page, empty, failed, noisy_unknown
    visible_chars INTEGER DEFAULT 0,
    line_count INTEGER DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    part_like_count INTEGER DEFAULT 0,
    confidence_score NUMERIC(5,4),
    text_hash TEXT,
    ocr_text_path TEXT,
    generated_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.nomenclature (
    nomenclature_id TEXT PRIMARY KEY,
    normalized_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE (normalized_name)
);

CREATE TABLE IF NOT EXISTS tiff_lib.parts (
    part_id TEXT PRIMARY KEY,
    normalized_part_number TEXT NOT NULL UNIQUE,
    display_part_number TEXT NOT NULL,
    canonical_nomenclature_id TEXT REFERENCES tiff_lib.nomenclature(nomenclature_id) ON DELETE SET NULL,
    confidence TEXT,
    first_seen_page_id TEXT REFERENCES tiff_lib.pages(page_id) ON DELETE SET NULL,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.part_mentions (
    part_mention_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES tiff_lib.pages(page_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES tiff_lib.documents(document_id) ON DELETE CASCADE,
    part_id TEXT NOT NULL REFERENCES tiff_lib.parts(part_id) ON DELETE CASCADE,
    ata_id TEXT REFERENCES tiff_lib.ata_sections(ata_id) ON DELETE SET NULL,
    mention_text TEXT,
    evidence_line TEXT,
    line_number INTEGER,
    extraction_method TEXT,
    confidence_score NUMERIC(5,4),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.page_contexts (
    page_context_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES tiff_lib.pages(page_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES tiff_lib.documents(document_id) ON DELETE CASCADE,
    short_summary TEXT NOT NULL,
    long_summary TEXT,
    page_role TEXT,
    confidence TEXT,
    score NUMERIC(5,4),
    model_name TEXT,
    prompt_version TEXT,
    source_ocr_hash TEXT,
    context_status TEXT DEFAULT 'generated', -- generated, empty_ocr_fallback, failed, needs_regeneration
    generated_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE (page_id)
);

CREATE TABLE IF NOT EXISTS tiff_lib.topics (
    topic_id TEXT PRIMARY KEY,
    normalized_topic TEXT NOT NULL UNIQUE,
    display_topic TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.page_context_topics (
    page_context_id TEXT NOT NULL REFERENCES tiff_lib.page_contexts(page_context_id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES tiff_lib.topics(topic_id) ON DELETE CASCADE,
    rank INTEGER DEFAULT 0,
    PRIMARY KEY (page_context_id, topic_id)
);

CREATE TABLE IF NOT EXISTS tiff_lib.rag_chunks (
    chunk_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES tiff_lib.pages(page_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES tiff_lib.documents(document_id) ON DELETE CASCADE,
    ata_id TEXT REFERENCES tiff_lib.ata_sections(ata_id) ON DELETE SET NULL,
    chunk_index INTEGER NOT NULL,
    chunk_type TEXT DEFAULT 'ocr_text', -- ocr_text, page_context, part_catalog, procedure
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    token_estimate INTEGER,
    qdrant_collection TEXT,
    qdrant_point_id TEXT,
    opensearch_index TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE (page_id, chunk_index, chunk_type)
);

CREATE TABLE IF NOT EXISTS tiff_lib.rag_retrieval_events (
    retrieval_id TEXT PRIMARY KEY,
    question_id TEXT,
    chunk_id TEXT REFERENCES tiff_lib.rag_chunks(chunk_id) ON DELETE SET NULL,
    page_id TEXT REFERENCES tiff_lib.pages(page_id) ON DELETE SET NULL,
    retriever TEXT NOT NULL, -- exact, opensearch, qdrant, graph
    score NUMERIC,
    rank INTEGER,
    payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tiff_lib.user_questions (
    question_id TEXT PRIMARY KEY,
    question_text TEXT NOT NULL,
    normalized_question TEXT,
    user_session_id TEXT,
    intent TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.answers (
    answer_id TEXT PRIMARY KEY,
    question_id TEXT REFERENCES tiff_lib.user_questions(question_id) ON DELETE SET NULL,
    answer_text TEXT NOT NULL,
    answer_type TEXT, -- exact_lookup, rag_summary, graph_trace, source_lookup
    llm_used BOOLEAN DEFAULT false,
    embeddings_used BOOLEAN DEFAULT false,
    model_name TEXT,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.answer_sources (
    answer_source_id TEXT PRIMARY KEY,
    answer_id TEXT NOT NULL REFERENCES tiff_lib.answers(answer_id) ON DELETE CASCADE,
    page_id TEXT REFERENCES tiff_lib.pages(page_id) ON DELETE SET NULL,
    source_link_id TEXT REFERENCES tiff_lib.source_links(source_link_id) ON DELETE SET NULL,
    chunk_id TEXT REFERENCES tiff_lib.rag_chunks(chunk_id) ON DELETE SET NULL,
    part_id TEXT REFERENCES tiff_lib.parts(part_id) ON DELETE SET NULL,
    source_rank INTEGER,
    score NUMERIC,
    evidence_text TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.user_feedback (
    feedback_id TEXT PRIMARY KEY,
    answer_id TEXT REFERENCES tiff_lib.answers(answer_id) ON DELETE SET NULL,
    question_id TEXT REFERENCES tiff_lib.user_questions(question_id) ON DELETE SET NULL,
    rating TEXT NOT NULL, -- up, down, neutral, 1..5
    category TEXT, -- useful, wrong_answer, wrong_source, missing_source, incomplete, too_verbose, ocr_issue, other
    reason TEXT,
    user_session_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.qa_findings (
    qa_finding_id TEXT PRIMARY KEY,
    severity TEXT NOT NULL, -- ok, info, review, fail
    category TEXT NOT NULL,
    entity_type TEXT NOT NULL, -- page, part, source_link, ocr_record, answer, feedback
    entity_id TEXT NOT NULL,
    finding_text TEXT NOT NULL,
    status TEXT DEFAULT 'open', -- open, suppressed, resolved
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.file_state (
    file_state_id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    file_type TEXT,
    byte_size BIGINT,
    modified_at TIMESTAMPTZ,
    content_hash TEXT,
    last_seen_at TIMESTAMPTZ DEFAULT now(),
    last_processed_at TIMESTAMPTZ,
    processing_status TEXT DEFAULT 'seen', -- seen, queued, processed, failed, deleted
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.pipeline_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    manifest_path TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tiff_lib.quality_snapshots (
    quality_snapshot_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES tiff_lib.pipeline_runs(run_id) ON DELETE SET NULL,
    quality_status TEXT NOT NULL,
    summary JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Core lookup indexes
CREATE INDEX IF NOT EXISTS idx_pages_document ON tiff_lib.pages(document_id);
CREATE INDEX IF NOT EXISTS idx_pages_ata ON tiff_lib.pages(ata_id);
CREATE INDEX IF NOT EXISTS idx_pages_page_number ON tiff_lib.pages(document_id, page_number);
CREATE INDEX IF NOT EXISTS idx_source_links_page ON tiff_lib.source_links(page_id);
CREATE INDEX IF NOT EXISTS idx_part_mentions_part ON tiff_lib.part_mentions(part_id);
CREATE INDEX IF NOT EXISTS idx_part_mentions_page ON tiff_lib.part_mentions(page_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_page ON tiff_lib.rag_chunks(page_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_qdrant ON tiff_lib.rag_chunks(qdrant_collection, qdrant_point_id);
CREATE INDEX IF NOT EXISTS idx_feedback_answer ON tiff_lib.user_feedback(answer_id);
CREATE INDEX IF NOT EXISTS idx_file_state_hash ON tiff_lib.file_state(content_hash);

-- JSONB helper indexes for filtering metadata when needed.
CREATE INDEX IF NOT EXISTS idx_pages_metadata_gin ON tiff_lib.pages USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_page_contexts_metadata_gin ON tiff_lib.page_contexts USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_quality_snapshots_summary_gin ON tiff_lib.quality_snapshots USING GIN (summary);
"""


def opensearch_mappings() -> Dict[str, Any]:
    """Return OpenSearch mapping drafts."""

    common_settings = {
        "number_of_shards": 3,
        "number_of_replicas": 1,
        "analysis": {
            "normalizer": {
                "lowercase_keyword": {
                    "type": "custom",
                    "filter": ["lowercase", "asciifolding"],
                }
            },
            "analyzer": {
                "technical_text": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding"],
                }
            },
        },
    }

    keyword = {"type": "keyword", "normalizer": "lowercase_keyword"}
    text = {"type": "text", "analyzer": "technical_text"}

    return {
        "tiff_pages_v1": {
            "settings": common_settings,
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "page_id": keyword,
                    "document_id": keyword,
                    "manual_title": text,
                    "ata_code": keyword,
                    "page_label": keyword,
                    "page_number": {"type": "integer"},
                    "page_role": keyword,
                    "ocr_text": text,
                    "ocr_depth_classification": keyword,
                    "part_numbers": {"type": "keyword"},
                    "nomenclature": text,
                    "topics": {"type": "keyword"},
                    "source_link_id": keyword,
                    "source_url": {"type": "keyword", "index": False},
                    "rescarta_url": {"type": "keyword", "index": False},
                    "ocr_hash": keyword,
                    "updated_at": {"type": "date"},
                },
            },
        },
        "tiff_rag_chunks_v1": {
            "settings": common_settings,
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "chunk_id": keyword,
                    "page_id": keyword,
                    "document_id": keyword,
                    "ata_code": keyword,
                    "chunk_index": {"type": "integer"},
                    "chunk_type": keyword,
                    "text": text,
                    "text_hash": keyword,
                    "part_numbers": {"type": "keyword"},
                    "source_link_id": keyword,
                    "qdrant_collection": keyword,
                    "qdrant_point_id": keyword,
                    "updated_at": {"type": "date"},
                },
            },
        },
        "tiff_page_contexts_v1": {
            "settings": common_settings,
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "page_context_id": keyword,
                    "page_id": keyword,
                    "document_id": keyword,
                    "ata_code": keyword,
                    "short_summary": text,
                    "long_summary": text,
                    "page_role": keyword,
                    "confidence": keyword,
                    "score": {"type": "float"},
                    "topics": {"type": "keyword"},
                    "highlighted_parts": {"type": "keyword"},
                    "context_status": keyword,
                    "model_name": keyword,
                    "prompt_version": keyword,
                    "source_ocr_hash": keyword,
                    "generated_at": {"type": "date"},
                },
            },
        },
        "tiff_parts_v1": {
            "settings": common_settings,
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "part_id": keyword,
                    "normalized_part_number": keyword,
                    "display_part_number": keyword,
                    "nomenclature": text,
                    "ata_codes": {"type": "keyword"},
                    "document_ids": {"type": "keyword"},
                    "page_ids": {"type": "keyword"},
                    "source_count": {"type": "integer"},
                    "updated_at": {"type": "date"},
                },
            },
        },
    }


def qdrant_collections(vector_size: int = 1024, distance: str = "Cosine") -> Dict[str, Any]:
    """Return Qdrant collection drafts.

    bge-m3 embeddings are commonly 1024-dimensional, so 1024 is the default.
    Keep vector bytes out of PostgreSQL and store only qdrant point IDs there.
    """

    return {
        "tiff_rag_chunks_v1": {
            "vectors": {"size": vector_size, "distance": distance},
            "payload_schema": {
                "chunk_id": "keyword",
                "page_id": "keyword",
                "document_id": "keyword",
                "ata_code": "keyword",
                "source_link_id": "keyword",
                "chunk_type": "keyword",
                "part_numbers": "keyword[]",
                "text_hash": "keyword",
                "ocr_hash": "keyword",
                "visibility_scope": "keyword",
                "updated_at": "datetime",
            },
            "payload_indexes": [
                "chunk_id",
                "page_id",
                "document_id",
                "ata_code",
                "source_link_id",
                "part_numbers",
                "chunk_type",
            ],
        },
        "tiff_page_contexts_v1": {
            "vectors": {"size": vector_size, "distance": distance},
            "payload_schema": {
                "page_context_id": "keyword",
                "page_id": "keyword",
                "document_id": "keyword",
                "ata_code": "keyword",
                "page_role": "keyword",
                "topics": "keyword[]",
                "highlighted_parts": "keyword[]",
                "score": "float",
                "source_ocr_hash": "keyword",
                "visibility_scope": "keyword",
                "updated_at": "datetime",
            },
            "payload_indexes": [
                "page_context_id",
                "page_id",
                "document_id",
                "ata_code",
                "page_role",
                "topics",
                "highlighted_parts",
            ],
        },
        "tiff_image_pages_v1_future": {
            "status": "future_optional",
            "purpose": "Image embeddings for diagrams, empty OCR pages, uploaded images, and visual similarity.",
            "vectors": {"size": 1024, "distance": distance},
            "payload_schema": {
                "page_id": "keyword",
                "document_id": "keyword",
                "ata_code": "keyword",
                "source_image_uri": "keyword",
                "image_hash": "keyword",
                "page_role": "keyword",
                "visibility_scope": "keyword",
                "updated_at": "datetime",
            },
            "payload_indexes": ["page_id", "document_id", "ata_code", "image_hash", "page_role"],
        },
    }


def storage_migration_plan_md() -> str:
    """Return a migration plan document."""

    return """# Production Storage Migration Draft

## Goal

Move from the local MVP shape:

```text
Streamlit UI -> FastAPI -> service layer -> storage adapters -> local JSON/SQLite artifacts
```

to the production shape:

```text
Streamlit UI -> FastAPI -> service layer -> storage adapters -> PostgreSQL / OpenSearch / Qdrant / ResCarta
```

The API contract should remain stable while the adapter implementations change.

## Storage responsibilities

### PostgreSQL

PostgreSQL is the system of record for structured data and graph relationships:

- documents
- pages
- ATA sections
- source files
- source links
- OCR records
- parts
- nomenclature
- part mentions
- page contexts
- RAG chunk metadata
- feedback
- QA findings
- file state
- pipeline/quality snapshots

PostgreSQL should not store TIFF bytes or dense vector arrays.

### OpenSearch

OpenSearch is the keyword and full-text retrieval layer:

- OCR page text
- RAG chunk text
- page context summaries
- part/nomenclature search documents

OpenSearch stores denormalized searchable documents. PostgreSQL remains the truth source.

### Qdrant

Qdrant stores dense embeddings and small payloads:

- chunk embeddings
- page-context embeddings
- future optional image/page embeddings

Payloads must include `chunk_id` and/or `page_id` so the backend can resolve the result through PostgreSQL graph relationships.

### ResCarta / file storage

ResCarta or file storage remains the source of raw TIFFs and source viewing links. The derived databases store IDs, paths, URIs, hashes, and metadata only.

## Critical traceability invariant

Every answer should be able to trace back:

```text
answer -> answer_sources -> rag_chunk/page/part -> page -> document/ATA -> source_link -> TIFF/OCR source
```

Every Qdrant result must be resolvable:

```text
qdrant point -> chunk_id/page_id -> PostgreSQL graph -> source link/context
```

## Migration phases

1. Keep local adapters as the reference implementation.
2. Add PostgreSQL schema and read-only migration writer for the 509-page sample.
3. Add PostgreSQL-backed `CatalogStore`, `TraceStore`, `FeedbackStore`, and `QualityStore`.
4. Add OpenSearch indexing for OCR pages/chunks/context.
5. Add Qdrant indexing for chunk/context embeddings.
6. Run API contract tests against production adapters.
7. Compare local adapter results and production adapter results on the 509-page sample.
8. Only then pilot on a real server batch.

## Pre-server guardrails

- Do not OCR the full server on first access.
- Do not embed the full server on first access.
- Do not generate AI page context for every page at production scale without a selective/on-demand strategy.
- Start with inventory, OCR-depth audit, source traceability, and a small pilot batch.
"""


def generated_artifacts() -> List[SchemaArtifact]:
    """Return all schema artifacts to write."""

    return [
        SchemaArtifact(
            relative_path="postgres_schema.sql",
            content=postgres_schema_sql(),
            description="PostgreSQL relational/graph schema draft",
        ),
        SchemaArtifact(
            relative_path="opensearch_mappings.json",
            content=json.dumps(opensearch_mappings(), indent=2, sort_keys=True),
            description="OpenSearch index mapping draft",
        ),
        SchemaArtifact(
            relative_path="qdrant_collections.json",
            content=json.dumps(qdrant_collections(), indent=2, sort_keys=True),
            description="Qdrant collection and payload draft",
        ),
        SchemaArtifact(
            relative_path="storage_migration_plan.md",
            content=storage_migration_plan_md(),
            description="Storage migration and responsibility plan",
        ),
    ]


def write_schema_drafts(output_dir: Path = DEFAULT_OUTPUT_DIR) -> SchemaDraftSummary:
    """Write schema artifacts and return a summary."""

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = generated_artifacts()
    for artifact in artifacts:
        path = output_dir / artifact.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content.rstrip() + "\n", encoding="utf-8")

    summary = SchemaDraftSummary(
        status="OK",
        schema_version=SCHEMA_VERSION,
        output_dir=str(output_dir),
        artifacts_written=len(artifacts) + 1,
        postgres_tables=list(POSTGRES_TABLES),
        opensearch_indices=list(OPENSEARCH_INDICES),
        qdrant_collections=list(QDRANT_COLLECTIONS),
        notes=[
            "Draft only; does not connect to production services.",
            "PostgreSQL stores graph/catalog/source/feedback/quality metadata, not TIFF bytes.",
            "Qdrant payloads must include page_id/chunk_id for graph traceability.",
            "OpenSearch indexes denormalized OCR/chunk/context text for keyword retrieval.",
        ],
    )
    summary_payload = summary.to_dict()
    summary_payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    (output_dir / "production_schema_summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def validate_schema_drafts(output_dir: Path = DEFAULT_OUTPUT_DIR) -> List[str]:
    """Return validation issues for generated schema drafts."""

    issues: List[str] = []
    expected_files = [artifact.relative_path for artifact in generated_artifacts()] + ["production_schema_summary.json"]
    for rel in expected_files:
        path = output_dir / rel
        if not path.exists():
            issues.append(f"missing artifact: {rel}")
        elif path.stat().st_size == 0:
            issues.append(f"empty artifact: {rel}")

    postgres_path = output_dir / "postgres_schema.sql"
    if postgres_path.exists():
        sql = postgres_path.read_text(encoding="utf-8")
        for table in POSTGRES_TABLES:
            if f"tiff_lib.{table}" not in sql:
                issues.append(f"postgres table not found in SQL: {table}")

    opensearch_path = output_dir / "opensearch_mappings.json"
    if opensearch_path.exists():
        data = json.loads(opensearch_path.read_text(encoding="utf-8"))
        for index in OPENSEARCH_INDICES:
            if index not in data:
                issues.append(f"opensearch index missing: {index}")

    qdrant_path = output_dir / "qdrant_collections.json"
    if qdrant_path.exists():
        data = json.loads(qdrant_path.read_text(encoding="utf-8"))
        for collection in QDRANT_COLLECTIONS:
            if collection not in data:
                issues.append(f"qdrant collection missing: {collection}")

    return issues
