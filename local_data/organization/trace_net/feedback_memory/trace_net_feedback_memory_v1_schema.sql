create table if not exists trace_net_feedback_events (
  feedback_id text primary key,
  created_at timestamptz not null default now(),
  schema_version text not null,
  user_id_hash text,
  session_id text,
  query_text text,
  query_hash text,
  answer_report_id text,
  answer_mode text,
  retrieval_mode text,
  target_type text not null,
  target_id text,
  rating smallint not null,
  comment_text text,
  issue_tags jsonb not null default '[]'::jsonb,
  page_ids jsonb not null default '[]'::jsonb,
  citation_ids jsonb not null default '[]'::jsonb,
  claim_ids jsonb not null default '[]'::jsonb,
  community_ids jsonb not null default '[]'::jsonb,
  source_artifact_path text,
  safety_status text not null default 'raw_feedback_unreviewed',
  prompt_injection_flagged boolean not null default false,
  pii_or_secret_flagged boolean not null default false,
  local_path_flagged boolean not null default false,
  can_mutate_source_truth boolean not null default false,
  can_prove_claims boolean not null default false,
  can_answer_directly boolean not null default false,
  raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists idx_trace_net_feedback_events_query_hash
  on trace_net_feedback_events(query_hash);
create index if not exists idx_trace_net_feedback_events_target
  on trace_net_feedback_events(target_type, target_id);
create index if not exists idx_trace_net_feedback_events_created_at
  on trace_net_feedback_events(created_at);

create table if not exists trace_net_feedback_memory_records (
  memory_id text primary key,
  created_at timestamptz not null default now(),
  schema_version text not null,
  source_feedback_ids jsonb not null default '[]'::jsonb,
  query_hash text,
  query_text_redacted text,
  target_type text not null,
  target_id text,
  page_ids jsonb not null default '[]'::jsonb,
  citation_ids jsonb not null default '[]'::jsonb,
  claim_ids jsonb not null default '[]'::jsonb,
  community_ids jsonb not null default '[]'::jsonb,
  feedback_summary text not null,
  feedback_signal text not null,
  rating_score numeric not null default 0,
  authority text not null default 'feedback_advisory_only',
  record_type text not null default 'feedback_memory',
  safety_bucket text not null default 'feedback_memory_advisory',
  llm_reference_allowed boolean not null default true,
  retrieval_advisory_allowed boolean not null default true,
  can_answer_directly boolean not null default false,
  can_prove_claims boolean not null default false,
  can_mutate_source_truth boolean not null default false,
  requires_source_resolution boolean not null default true,
  requires_citation boolean not null default true,
  requires_authority_gate boolean not null default true,
  reviewed boolean not null default false,
  review_status text not null default 'unreviewed',
  sanitized_payload jsonb not null default '{}'::jsonb
);

create index if not exists idx_trace_net_feedback_memory_target
  on trace_net_feedback_memory_records(target_type, target_id);
create index if not exists idx_trace_net_feedback_memory_query_hash
  on trace_net_feedback_memory_records(query_hash);
create index if not exists idx_trace_net_feedback_memory_created_at
  on trace_net_feedback_memory_records(created_at);
