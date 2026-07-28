-- Durable queue operations must be atomic because the stdlib PostgREST client
-- cannot issue BEGIN / SELECT FOR UPDATE directly.  The service-role worker
-- invokes these RPCs; no browser credentials are involved.
alter table public.research_jobs
  add column if not exists payload jsonb not null default '{}'::jsonb,
  add column if not exists usage jsonb not null default '{}'::jsonb,
  add column if not exists cancel_requested_at timestamptz,
  add column if not exists last_heartbeat_at timestamptz,
  add column if not exists lease_token uuid,
  add column if not exists attempt_count integer not null default 0 check (attempt_count >= 0);

create index if not exists research_jobs_claim_order_idx
  on public.research_jobs (requested_at, id) where status = 'queued';
create index if not exists research_jobs_expired_lease_idx
  on public.research_jobs (lease_expires_at) where status in ('leased', 'running');

create or replace function public.fieldnote_claim_research_job(
  p_worker_id text,
  p_lease_seconds integer default 60,
  p_max_active integer default 2
) returns setof public.research_jobs
language plpgsql security definer set search_path = public as $$
declare
  candidate public.research_jobs;
  active_count integer;
  seconds integer := greatest(10, least(coalesce(p_lease_seconds, 60), 3600));
  slots integer := greatest(1, least(coalesce(p_max_active, 2), 2));
begin
  if nullif(trim(p_worker_id), '') is null then raise exception 'worker id is required'; end if;
  -- One short transaction-wide lock makes the count-and-claim slot limit real
  -- across processes, while SKIP LOCKED keeps product jobs independently claimable.
  perform pg_advisory_xact_lock(hashtext('fieldnote_research_job_slots'));
  update public.research_jobs
     set status = 'queued', lease_owner = null, lease_token = null,
         lease_expires_at = null, last_heartbeat_at = null
   where status in ('leased', 'running') and lease_expires_at <= clock_timestamp();
  select count(*) into active_count from public.research_jobs
   where status in ('leased', 'running') and lease_expires_at > clock_timestamp();
  if active_count >= slots then return; end if;
  select * into candidate from public.research_jobs
   where status = 'queued' and cancel_requested_at is null
   order by requested_at, id for update skip locked limit 1;
  if not found then return; end if;
  update public.research_jobs
     set status = 'leased', lease_owner = p_worker_id, lease_token = gen_random_uuid(),
         lease_expires_at = clock_timestamp() + make_interval(secs => seconds),
         last_heartbeat_at = clock_timestamp(), started_at = coalesce(started_at, clock_timestamp()),
         attempt_count = attempt_count + 1
   where id = candidate.id returning * into candidate;
  insert into public.research_job_events(job_id, event_type, payload)
    values (candidate.id, 'leased', jsonb_build_object('worker_id', p_worker_id, 'attempt', candidate.attempt_count));
  return next candidate;
end; $$;

create or replace function public.fieldnote_start_research_job(p_job_id text, p_lease_token uuid)
returns setof public.research_jobs language plpgsql security definer set search_path = public as $$
declare value public.research_jobs;
begin
  update public.research_jobs set status = 'running', last_heartbeat_at = clock_timestamp()
   where job_id = p_job_id and status = 'leased' and lease_token = p_lease_token
     and lease_expires_at > clock_timestamp() returning * into value;
  if found then insert into public.research_job_events(job_id, event_type) values (value.id, 'running'); return next value; end if;
end; $$;

create or replace function public.fieldnote_heartbeat_research_job(p_job_id text, p_lease_token uuid, p_lease_seconds integer default 60)
returns setof public.research_jobs language plpgsql security definer set search_path = public as $$
declare value public.research_jobs; seconds integer := greatest(10, least(coalesce(p_lease_seconds, 60), 3600));
begin
  update public.research_jobs set lease_expires_at = clock_timestamp() + make_interval(secs => seconds), last_heartbeat_at = clock_timestamp()
   where job_id = p_job_id and status in ('leased', 'running') and lease_token = p_lease_token
     and lease_expires_at > clock_timestamp() returning * into value;
  if found then return next value; end if;
end; $$;

create or replace function public.fieldnote_request_research_job_cancel(p_job_id text)
returns setof public.research_jobs language plpgsql security definer set search_path = public as $$
declare value public.research_jobs;
begin
  update public.research_jobs set
    status = case when status = 'queued' then 'cancelled'::public.research_job_status else status end,
    cancel_requested_at = clock_timestamp(),
    completed_at = case when status = 'queued' then clock_timestamp() else completed_at end
   where job_id = p_job_id and status in ('queued', 'leased', 'running') returning * into value;
  if found then insert into public.research_job_events(job_id, event_type) values (value.id, 'cancel_requested'); return next value; end if;
end; $$;

create or replace function public.fieldnote_complete_research_job(
  p_job_id text, p_lease_token uuid, p_status public.research_job_status,
  p_result jsonb default '{}'::jsonb, p_usage jsonb default '{}'::jsonb, p_cost_used numeric default 0
) returns setof public.research_jobs language plpgsql security definer set search_path = public as $$
declare value public.research_jobs; final_status public.research_job_status;
begin
  if p_status not in ('partial', 'succeeded', 'failed', 'cancelled') then raise exception 'invalid terminal job status'; end if;
  update public.research_jobs set
    status = case when cancel_requested_at is not null then 'cancelled'::public.research_job_status else p_status end,
    result = coalesce(p_result, '{}'::jsonb), usage = coalesce(p_usage, '{}'::jsonb),
    cost_used = greatest(0, coalesce(p_cost_used, 0)), completed_at = clock_timestamp(),
    lease_expires_at = null, lease_owner = null, lease_token = null
   where job_id = p_job_id and status in ('leased', 'running') and lease_token = p_lease_token
   returning * into value;
  if found then insert into public.research_job_events(job_id, event_type, payload)
    values (value.id, value.status::text, jsonb_build_object('usage', value.usage, 'cost_used', value.cost_used)); return next value; end if;
end; $$;

revoke all on function public.fieldnote_claim_research_job(text, integer, integer) from public;
revoke all on function public.fieldnote_start_research_job(text, uuid) from public;
revoke all on function public.fieldnote_heartbeat_research_job(text, uuid, integer) from public;
revoke all on function public.fieldnote_request_research_job_cancel(text) from public;
revoke all on function public.fieldnote_complete_research_job(text, uuid, public.research_job_status, jsonb, jsonb, numeric) from public;

-- The API and worker use the server-only service-role key. Browser roles keep
-- RLS table access and cannot invoke queue state transitions directly.
grant execute on function public.fieldnote_claim_research_job(text, integer, integer) to service_role;
grant execute on function public.fieldnote_start_research_job(text, uuid) to service_role;
grant execute on function public.fieldnote_heartbeat_research_job(text, uuid, integer) to service_role;
grant execute on function public.fieldnote_request_research_job_cancel(text) to service_role;
grant execute on function public.fieldnote_complete_research_job(text, uuid, public.research_job_status, jsonb, jsonb, numeric) to service_role;
