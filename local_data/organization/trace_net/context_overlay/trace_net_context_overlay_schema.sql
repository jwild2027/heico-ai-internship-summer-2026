
CREATE TABLE IF NOT EXISTS trace_net_context_overlay_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    overlay_version TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source_kind TEXT NOT NULL DEFAULT 'local_context_summary',
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    authority_scope TEXT NOT NULL DEFAULT 'project_context_only',
    answer_authority TEXT NOT NULL DEFAULT 'none',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trace_net_context_overlay_items (
    item_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES trace_net_context_overlay_snapshots(snapshot_id) ON DELETE CASCADE,
    item_type TEXT NOT NULL,
    item_key TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    source_ref TEXT,
    authority_scope TEXT NOT NULL DEFAULT 'project_context_only',
    answer_authority TEXT NOT NULL DEFAULT 'none',
    allowed_usage JSONB NOT NULL DEFAULT '["operator_context", "routing_context"]'::jsonb,
    blocked_usage JSONB NOT NULL DEFAULT '["manual_answer_evidence", "source_text_evidence", "verified_part_evidence"]'::jsonb,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, item_type, item_key)
);

CREATE TABLE IF NOT EXISTS trace_net_context_overlay_edges (
    edge_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES trace_net_context_overlay_snapshots(snapshot_id) ON DELETE CASCADE,
    source_item_id TEXT NOT NULL REFERENCES trace_net_context_overlay_items(item_id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,
    target_item_id TEXT NOT NULL REFERENCES trace_net_context_overlay_items(item_id) ON DELETE CASCADE,
    authority_scope TEXT NOT NULL DEFAULT 'project_context_only',
    answer_authority TEXT NOT NULL DEFAULT 'none',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, source_item_id, edge_type, target_item_id)
);

CREATE TABLE IF NOT EXISTS trace_net_context_overlay_metrics (
    metric_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES trace_net_context_overlay_snapshots(snapshot_id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL,
    metric_label TEXT NOT NULL,
    metric_value NUMERIC,
    metric_unit TEXT NOT NULL DEFAULT 'count',
    authority_scope TEXT NOT NULL DEFAULT 'project_context_only',
    answer_authority TEXT NOT NULL DEFAULT 'none',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, metric_key)
);

CREATE INDEX IF NOT EXISTS idx_trace_net_context_items_snapshot_type
    ON trace_net_context_overlay_items(snapshot_id, item_type);
CREATE INDEX IF NOT EXISTS idx_trace_net_context_items_payload_gin
    ON trace_net_context_overlay_items USING GIN(payload);
CREATE INDEX IF NOT EXISTS idx_trace_net_context_edges_snapshot_type
    ON trace_net_context_overlay_edges(snapshot_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_trace_net_context_metrics_snapshot_key
    ON trace_net_context_overlay_metrics(snapshot_id, metric_key);
