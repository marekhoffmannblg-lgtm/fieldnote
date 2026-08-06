create table public.product_refresh_runs (
  id uuid primary key default gen_random_uuid(),
  run_id text not null unique,
  product_id text not null references public.products(product_id) on delete restrict,
  requested_by uuid references auth.users(id) on delete set null,
  configuration text not null default '',
  status text not null check (status in ('running','succeeded','partial','failed','cancelled','no_change')),
  result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create table public.product_refresh_snapshots (
  id uuid primary key default gen_random_uuid(),
  product_id text not null references public.products(product_id) on delete restrict,
  source_id text not null references public.sources(source_id) on delete restrict,
  canonical_url text not null,
  content_hash text not null,
  raw_object_path text not null,
  clean_object_path text not null,
  classification text not null default 'exact_match',
  fetch_status text not null default 'stored',
  created_at timestamptz not null default now(),
  unique (source_id, content_hash)
);

create table public.product_refresh_run_sources (
  id uuid primary key default gen_random_uuid(),
  run_id text not null references public.product_refresh_runs(run_id) on delete cascade,
  snapshot_id uuid not null references public.product_refresh_snapshots(id) on delete restrict,
  product_id text not null references public.products(product_id) on delete restrict,
  raw_object_path text not null,
  clean_object_path text not null,
  created_at timestamptz not null default now(),
  unique (run_id, snapshot_id)
);

alter table public.product_refresh_runs enable row level security;
alter table public.product_refresh_snapshots enable row level security;
alter table public.product_refresh_run_sources enable row level security;
grant select, insert, update, delete on public.product_refresh_runs to authenticated;
grant select, insert, update, delete on public.product_refresh_snapshots to authenticated;
grant select, insert, update, delete on public.product_refresh_run_sources to authenticated;
create policy product_refresh_read on public.product_refresh_runs for select to authenticated using (public.fieldnote_can_read());
create policy product_refresh_write on public.product_refresh_runs for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy product_refresh_snapshots_read on public.product_refresh_snapshots for select to authenticated using (public.fieldnote_can_read());
create policy product_refresh_snapshots_write on public.product_refresh_snapshots for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy product_refresh_run_sources_read on public.product_refresh_run_sources for select to authenticated using (public.fieldnote_can_read());
create policy product_refresh_run_sources_write on public.product_refresh_run_sources for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
