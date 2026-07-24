create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  role public.fieldnote_role not null default 'viewer',
  must_change_password boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.fieldnote_current_role()
returns public.fieldnote_role
language sql stable security definer set search_path = public
as $$ select role from public.profiles where id = auth.uid() $$;

create or replace function public.fieldnote_password_change_required()
returns boolean
language sql stable security definer set search_path = public
as $$ select coalesce((select must_change_password from public.profiles where id = auth.uid()), true) $$;

create or replace function public.fieldnote_can_read()
returns boolean
language sql stable security definer set search_path = public
as $$ select auth.uid() is not null and not public.fieldnote_password_change_required() $$;

create or replace function public.fieldnote_can_write_data()
returns boolean
language sql stable security definer set search_path = public
as $$ select public.fieldnote_current_role() in ('analyst', 'admin') and not public.fieldnote_password_change_required() $$;

create or replace function public.fieldnote_is_admin()
returns boolean
language sql stable security definer set search_path = public
as $$ select public.fieldnote_current_role() = 'admin' and not public.fieldnote_password_change_required() $$;

revoke all on function public.fieldnote_current_role() from public;
revoke all on function public.fieldnote_password_change_required() from public;
revoke all on function public.fieldnote_can_read() from public;
revoke all on function public.fieldnote_can_write_data() from public;
revoke all on function public.fieldnote_is_admin() from public;
grant execute on function public.fieldnote_current_role() to authenticated;
grant execute on function public.fieldnote_password_change_required() to authenticated;
grant execute on function public.fieldnote_can_read() to authenticated;
grant execute on function public.fieldnote_can_write_data() to authenticated;
grant execute on function public.fieldnote_is_admin() to authenticated;

alter table public.brands enable row level security;
alter table public.products enable row level security;
alter table public.product_aliases enable row level security;
alter table public.product_skus enable row level security;
alter table public.attribute_schema_versions enable row level security;
alter table public.product_profile_overrides enable row level security;
alter table public.sources enable row level security;
alter table public.product_source_links enable row level security;
alter table public.content_families enable row level security;
alter table public.source_snapshots enable row level security;
alter table public.evidence_items enable row level security;
alter table public.attribute_values enable row level security;
alter table public.attribute_value_candidates enable row level security;
alter table public.sellers enable row level security;
alter table public.offers enable row level security;
alter table public.price_observations enable row level security;
alter table public.availability_observations enable row level security;
alter table public.competitive_benchmarks enable row level security;
alter table public.competitive_benchmark_participants enable row level security;
alter table public.benchmark_results enable row level security;
alter table public.benchmark_snapshots enable row level security;
alter table public.research_jobs enable row level security;
alter table public.research_job_events enable row level security;
alter table public.import_runs enable row level security;
alter table public.audit_events enable row level security;
alter table public.profiles enable row level security;

create policy authenticated_read on public.brands for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.products for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.product_aliases for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.product_skus for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.attribute_schema_versions for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.sources for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.product_source_links for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.content_families for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.source_snapshots for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.evidence_items for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.attribute_values for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.attribute_value_candidates for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.sellers for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.offers for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.price_observations for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.availability_observations for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.competitive_benchmarks for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.competitive_benchmark_participants for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.benchmark_results for select to authenticated using (public.fieldnote_can_read());
create policy authenticated_read on public.benchmark_snapshots for select to authenticated using (public.fieldnote_can_read());
create policy own_profile_read on public.profiles for select to authenticated using (id = auth.uid());
create policy admin_profile_read on public.profiles for select to authenticated using (public.fieldnote_is_admin());
create policy admin_profile_manage on public.profiles for all to authenticated using (public.fieldnote_is_admin()) with check (public.fieldnote_is_admin());

create policy analyst_write on public.product_profile_overrides for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.sources for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.product_source_links for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.source_snapshots for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.evidence_items for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.attribute_values for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.attribute_value_candidates for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.sellers for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.offers for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.price_observations for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.availability_observations for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.research_jobs for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.research_job_events for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.import_runs for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.audit_events for insert to authenticated with check (public.fieldnote_can_write_data());
create policy analyst_write on public.competitive_benchmarks for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.competitive_benchmark_participants for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.benchmark_results for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy analyst_write on public.benchmark_snapshots for all to authenticated using (public.fieldnote_can_write_data()) with check (public.fieldnote_can_write_data());
create policy admin_write on public.brands for all to authenticated using (public.fieldnote_is_admin()) with check (public.fieldnote_is_admin());
create policy admin_write on public.products for all to authenticated using (public.fieldnote_is_admin()) with check (public.fieldnote_is_admin());
create policy admin_write on public.product_aliases for all to authenticated using (public.fieldnote_is_admin()) with check (public.fieldnote_is_admin());
create policy admin_write on public.product_skus for all to authenticated using (public.fieldnote_is_admin()) with check (public.fieldnote_is_admin());
create policy admin_write on public.attribute_schema_versions for all to authenticated using (public.fieldnote_is_admin()) with check (public.fieldnote_is_admin());
create policy admin_write on public.content_families for all to authenticated using (public.fieldnote_is_admin()) with check (public.fieldnote_is_admin());

insert into storage.buckets (id, name, public, file_size_limit)
values
  ('source-raw', 'source-raw', false, 26214400),
  ('source-clean', 'source-clean', false, 26214400),
  ('imports', 'imports', false, 26214400)
on conflict (id) do update set public = excluded.public, file_size_limit = excluded.file_size_limit;

create policy authenticated_storage_read on storage.objects for select to authenticated
  using (bucket_id in ('source-raw', 'source-clean', 'imports') and public.fieldnote_can_write_data());
create policy analyst_storage_write on storage.objects for insert to authenticated
  with check (bucket_id in ('source-raw', 'source-clean', 'imports') and public.fieldnote_can_write_data());
create policy analyst_storage_update on storage.objects for update to authenticated
  using (bucket_id in ('source-raw', 'source-clean', 'imports') and public.fieldnote_can_write_data())
  with check (bucket_id in ('source-raw', 'source-clean', 'imports') and public.fieldnote_can_write_data());
create policy admin_storage_delete on storage.objects for delete to authenticated
  using (bucket_id in ('source-raw', 'source-clean', 'imports') and public.fieldnote_is_admin());
