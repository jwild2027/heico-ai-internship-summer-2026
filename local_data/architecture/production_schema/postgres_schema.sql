-- TIFF technical-library production schema draft
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
