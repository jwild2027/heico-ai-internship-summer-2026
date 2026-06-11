create table if not exists trace_net_synthetic_incident_events (
  incident_id text primary key,
  created_at timestamptz not null,
  updated_at timestamptz not null default now(),
  environment text not null default 'local',
  incident_source text not null default 'synthetic_console',
  synthetic_only boolean not null default true,
  origin_category text not null,
  origin_label text,
  severity text not null,
  status text not null default 'open',
  message text not null,
  recommended_action text,
  target_type text,
  target_id text,
  incident_tag text,
  randomly_generated boolean not null default false,
  random_template_id text,
  prompt_injection_flagged boolean not null default false,
  prompt_injection_reasons jsonb not null default '[]'::jsonb,
  affects_real_pipeline boolean not null default false,
  can_answer_directly boolean not null default false,
  can_prove_claims boolean not null default false,
  can_mutate_source_truth boolean not null default false,
  source_truth_mutation_allowed boolean not null default false,
  source_truth_mutations_performed integer not null default 0,
  raw_feedback_direct_to_llm boolean not null default false,
  retrieval_only_answer_allowed boolean not null default false,
  community_as_proof boolean not null default false,
  feedback_as_proof boolean not null default false,
  actor_id text,
  acknowledged_by text,
  acknowledged_at timestamptz,
  resolved_by text,
  resolved_at timestamptz,
  resolution_note text,
  payload jsonb not null default '{}'::jsonb
);

create index if not exists idx_trace_net_synthetic_incident_events_created_at on trace_net_synthetic_incident_events (created_at desc);
create index if not exists idx_trace_net_synthetic_incident_events_severity on trace_net_synthetic_incident_events (severity);
create index if not exists idx_trace_net_synthetic_incident_events_status on trace_net_synthetic_incident_events (status);
create index if not exists idx_trace_net_synthetic_incident_events_origin_category on trace_net_synthetic_incident_events (origin_category);
