-- TRACE-Net Engineering Engram feedback ledger v1
-- Safety: feedback rows are behavior memory only; they are not proof_context.
CREATE TABLE IF NOT EXISTS trace_net_engram_feedback_ledger_v1 (
    feedback_id TEXT PRIMARY KEY,
    source_question_id TEXT NOT NULL,
    feedback_source TEXT NOT NULL,
    rating TEXT NOT NULL,
    explanation TEXT NOT NULL,
    source_grade TEXT,
    critic_status TEXT,
    crag_status TEXT,
    recommended_memory_layer TEXT NOT NULL,
    recommended_memory_type TEXT NOT NULL,
    proof_role TEXT NOT NULL DEFAULT 'guidance_only',
    answer_permission BOOLEAN NOT NULL DEFAULT FALSE,
    source_truth_mutation_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trace_net_engram_memory_candidate_v1 (
    candidate_id TEXT PRIMARY KEY,
    feedback_id TEXT NOT NULL REFERENCES trace_net_engram_feedback_ledger_v1(feedback_id),
    memory_layer TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    proof_role TEXT NOT NULL DEFAULT 'guidance_only',
    candidate_rule TEXT NOT NULL,
    candidate_trigger TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_human_review',
    answer_permission BOOLEAN NOT NULL DEFAULT FALSE,
    source_truth_mutation_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
