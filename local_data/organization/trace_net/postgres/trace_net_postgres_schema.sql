create table if not exists trace_net_schema_version (
  schema_version text primary key,
  created_at timestamptz not null default now()
);

create table if not exists trace_net_load_runs (
  load_id text primary key,
  version text not null,
  source_zip_path text,
  ocr_export_dir text,
  organization_dir text,
  trace_net_dir text,
  summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists source_packages (
  source_package_id text primary key,
  source_zip_path text,
  page_count integer,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists documents (
  document_id text primary key,
  source_package_id text,
  title text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists pages (
  page_id text primary key,
  document_id text,
  page_number integer,
  page_label text,
  ata_code text,
  source_url text,
  tiff_path text,
  ocr_path text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists ocr_records (
  page_id text primary key references pages(page_id) on delete cascade,
  ocr_path text,
  status text,
  classification text,
  text text,
  chars integer,
  lines integer,
  words integer,
  part_like_count integer,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists graph_nodes (
  node_id text primary key,
  node_type text,
  label text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists graph_edges (
  edge_id text primary key,
  source_id text,
  target_id text,
  edge_type text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists evidence_consensus_records (
  record_id text primary key,
  page_id text,
  evidence_layer text,
  trust_tier text,
  rag_action text,
  repair_action text,
  usable_confidence numeric,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists stage5_decision_records (
  record_id text primary key,
  page_id text,
  evidence_layer text,
  selected_trust_tier text,
  selected_rag_action text,
  policy_controlled boolean,
  usable_confidence numeric,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists rag_eligibility_records (
  record_id text primary key,
  page_id text,
  rag_bucket text,
  rag_action text,
  trust_tier text,
  evidence_layer text,
  safe_for_rag boolean,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists rag_candidate_chunks (
  candidate_id text primary key,
  page_id text,
  candidate_type text,
  rag_bucket text,
  evidence_layer text,
  trust_tier text,
  usable_confidence numeric,
  text text,
  source_url text,
  tiff_path text,
  ocr_path text,
  safe_for_rag boolean,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists source_citations (
  citation_id text primary key,
  candidate_id text,
  page_id text,
  citation_text text,
  source_url text,
  tiff_path text,
  ocr_path text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists ask_runs (
  ask_run_id text primary key,
  query text,
  query_fingerprint text,
  feedback_mode text,
  answer_page_records integer,
  answer_evidence_records integer,
  unsafe_answer_groups integer,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists feedback_events (
  feedback_id text primary key,
  ask_run_id text,
  query_fingerprint text,
  rating text,
  reason_codes jsonb not null default '[]'::jsonb,
  affected_page_ids jsonb not null default '[]'::jsonb,
  expected_page_ids jsonb not null default '[]'::jsonb,
  context_status text,
  policy_signal_eligible boolean,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists feedback_policy_signals (
  signal_id text primary key,
  feedback_id text,
  query_fingerprint text,
  page_id text,
  signal_type text,
  weight numeric,
  reason text,
  context_status text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists quality_runs (
  quality_id text primary key,
  stage text,
  status text,
  summary jsonb not null default '{}'::jsonb,
  source_path text,
  created_at timestamptz not null default now()
);

create index if not exists idx_pages_document on pages(document_id);
create index if not exists idx_pages_source_url on pages(source_url);
create index if not exists idx_ocr_classification on ocr_records(classification);
create index if not exists idx_rag_candidates_page on rag_candidate_chunks(page_id);
create index if not exists idx_rag_candidates_bucket on rag_candidate_chunks(rag_bucket);
create index if not exists idx_rag_candidates_safe on rag_candidate_chunks(safe_for_rag);
create index if not exists idx_feedback_query on feedback_events(query_fingerprint);
create index if not exists idx_feedback_signals_query on feedback_policy_signals(query_fingerprint);
