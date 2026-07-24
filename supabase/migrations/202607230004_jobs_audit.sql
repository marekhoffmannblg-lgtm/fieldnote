create type public.research_job_status as enum ('queued', 'leased', 'running', 'partial', 'succeeded', 'failed', 'cancelled');

create table public.research_jobs (
  id uuid primary key default gen_random_uuid(),
  job_id text not null unique,
  product_id text not null references public.products(product_id) on delete restrict,
  status public.research_job_status not null default 'queued',
  requested_by uuid not null references auth.users(id),
  lease_owner text,
  lease_expires_at timestamptz,
  cost_limit numeric(12,2),
  cost_used numeric(12,2) not null default 0 check (cost_used >= 0),
  requested_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  result jsonb not null default '{}'::jsonb
);

create unique index research_jobs_one_active_per_product
  on public.research_jobs(product_id)
  where status in ('queued', 'leased', 'running');

create table public.research_job_events (
  id bigint generated always as identity primary key,
  job_id uuid not null references public.research_jobs(id) on delete cascade,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.import_runs (
  id uuid primary key default gen_random_uuid(),
  import_id text not null unique,
  status text not null,
  requested_by uuid not null references auth.users(id),
  object_path text,
  summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create table public.audit_events (
  id bigint generated always as identity primary key,
  actor_id uuid references auth.users(id) on delete set null,
  event_type text not null,
  entity_type text not null,
  entity_id text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
