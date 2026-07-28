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

-- Queue state is server-owned.  The browser may inspect jobs/events, but all
-- mutations go through the FastAPI/service-role RPCs below.  The broad grants
-- and analyst_write policy from the auth migration must not leave a DML path.
revoke insert, update, delete on table public.research_jobs, public.research_job_events from authenticated;
grant select on table public.research_jobs, public.research_job_events to authenticated;
drop policy if exists analyst_write on public.research_jobs;
drop policy if exists analyst_write on public.research_job_events;

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
  -- Recover only leases that are actually expired.  A cancellation is
  -- terminal even when the worker died, and a job cannot be requeued forever:
  -- attempt_count includes the current claim, so max_retries=1 permits the
  -- initial attempt plus one recovery attempt.
  with expired as (
    select j.id,
           j.cancel_requested_at is not null as was_cancelled,
           j.attempt_count,
           case
             when (j.payload #>> '{limits,max_retries}') ~ '^[0-9]+$'
               then greatest(1, least((j.payload #>> '{limits,max_retries}')::integer, 100))
             else 1
           end as max_retries
      from public.research_jobs j
     where j.status in ('leased', 'running')
       and j.lease_expires_at <= clock_timestamp()
     for update skip locked
  ), terminalized as (
    update public.research_jobs j
       set status = case
                      when e.was_cancelled then 'cancelled'::public.research_job_status
                      else 'failed'::public.research_job_status
                    end,
           result = case when e.was_cancelled then jsonb_build_object('reason', 'cancelled_lease_expired')
                         else jsonb_build_object('reason', 'max_retries_exhausted') end,
           completed_at = clock_timestamp(), lease_owner = null,
           lease_token = null, lease_expires_at = null,
           last_heartbeat_at = null
      from expired e
     where j.id = e.id and (e.was_cancelled or e.attempt_count > e.max_retries)
     returning j.id, j.status, j.result
  )
  insert into public.research_job_events(job_id, event_type, payload)
  select id, status::text, result from terminalized;

  update public.research_jobs j
     set status = 'queued', lease_owner = null, lease_token = null,
         lease_expires_at = null, last_heartbeat_at = null
   where j.status in ('leased', 'running') and j.lease_expires_at <= clock_timestamp()
     and j.cancel_requested_at is null
     and j.attempt_count <= case
       when (j.payload #>> '{limits,max_retries}') ~ '^[0-9]+$'
         then greatest(1, least((j.payload #>> '{limits,max_retries}')::integer, 100))
       else 1 end;
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

create or replace function public.fieldnote_count_research_jobs(p_product_id text default null)
returns bigint
language sql security definer set search_path = public as $$
  select count(*)::bigint from public.research_jobs
   where p_product_id is null or product_id = p_product_id;
$$;
revoke all on function public.fieldnote_count_research_jobs(text) from public;
grant execute on function public.fieldnote_count_research_jobs(text) to service_role;

-- API reads event history by public job_id through the repository; service
-- role remains the only actor able to write queue events.
