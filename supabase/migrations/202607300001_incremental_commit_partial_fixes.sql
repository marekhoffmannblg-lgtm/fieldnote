-- Unit 6 follow-up: preserve the applied 202607290001 migration and roll out
-- the corrected partial/no-mutation envelope as a monotonic upgrade.
create or replace function public.fieldnote_commit_incremental_research_job(
  p_job_id text,
  p_lease_token uuid,
  p_status public.research_job_status,
  p_result jsonb default '{}'::jsonb,
  p_usage jsonb default '{}'::jsonb,
  p_cost_used numeric default 0,
  p_scope jsonb default '{}'::jsonb,
  p_snapshots jsonb default '[]'::jsonb
) returns setof public.research_jobs
language plpgsql security definer set search_path = public as $$
declare
  value public.research_jobs;
  candidate jsonb;
  previous public.research_scope_snapshots;
  candidate_scope_type text;
  candidate_scope_id text;
  candidate_semantic_hash text;
  candidate_domain_hash text;
  candidate_price numeric;
  snapshot_updated boolean := false;
  should_snapshot boolean;
begin
  if p_status not in ('partial', 'succeeded', 'failed', 'cancelled') then
    raise exception 'invalid terminal job status';
  end if;
  if jsonb_typeof(p_scope) <> 'object' or jsonb_typeof(p_snapshots) <> 'array'
     or jsonb_array_length(p_snapshots) > 16 then
    raise exception 'invalid incremental commit envelope';
  end if;

  -- Keep fence validation, semantic comparison, snapshot insert and job
  -- terminalization in one transaction shared with future admin rebuilds.
  perform pg_advisory_xact_lock(hashtext('fieldnote_benchmark_incremental_commit'));
  select * into value from public.research_jobs
   where job_id = p_job_id and status in ('leased', 'running')
     and lease_token = p_lease_token and lease_expires_at > clock_timestamp()
   for update;
  if not found then return; end if;

  -- A preflight/timeout partial has no semantic envelope by design. Keep it
  -- fenced to the claimed product while recording no snapshot mutation.
  if coalesce(p_scope->>'product_id', '') = '' then
    if p_status = 'partial' and jsonb_array_length(p_snapshots) = 0 then
      p_scope := jsonb_build_object(
        'product_id', value.product_id,
        'scope_version', '1',
        'no_mutation', true
      );
    else
      raise exception 'scope product does not match fenced job';
    end if;
  elsif p_scope->>'product_id' <> value.product_id then
    raise exception 'scope product does not match fenced job';
  end if;

  if value.cancel_requested_at is null and p_status in ('partial', 'succeeded') then
    for candidate in select element from jsonb_array_elements(p_snapshots) as elements(element) loop
      if jsonb_typeof(candidate) <> 'object' then raise exception 'invalid snapshot'; end if;
      candidate_scope_type := candidate->>'scope_type';
      candidate_scope_id := candidate->>'scope_id';
      candidate_semantic_hash := candidate->>'semantic_hash';
      candidate_domain_hash := candidate->>'domain_hash';
      if candidate_scope_type not in ('product', 'benchmark_group', 'competitive_benchmark')
         or nullif(candidate_scope_id, '') is null
         or candidate_semantic_hash !~ '^[0-9a-f]{64}$'
         or candidate_domain_hash !~ '^[0-9a-f]{64}$'
         or jsonb_typeof(candidate->'payload') <> 'object' then
        raise exception 'invalid snapshot fields';
      end if;
      if candidate_scope_type = 'product' and candidate_scope_id <> value.product_id then
        raise exception 'product snapshot scope does not match fenced job';
      end if;
      begin
        candidate_price := nullif(candidate->>'price_median', '')::numeric;
      exception when invalid_text_representation then
        raise exception 'invalid snapshot price';
      end;
      select * into previous from public.research_scope_snapshots
       where scope_type = candidate_scope_type and scope_id = candidate_scope_id
       order by created_at desc limit 1;
      should_snapshot := not found
        or previous.domain_hash <> candidate_domain_hash
        or (candidate_price is not null and previous.price_median is null)
        or (candidate_price is not null and previous.price_median = 0 and candidate_price <> 0)
        or (candidate_price is not null and previous.price_median <> 0
            and abs(candidate_price - previous.price_median) / abs(previous.price_median) >= 0.05);
      if should_snapshot then
        insert into public.research_scope_snapshots (
          scope_type, scope_id, semantic_hash, domain_hash, price_median, payload, research_job_id
        ) values (
          candidate_scope_type, candidate_scope_id, candidate_semantic_hash,
          candidate_domain_hash, candidate_price, candidate->'payload', value.id
        ) on conflict (scope_type, scope_id, semantic_hash) do nothing;
        if found then snapshot_updated := true; end if;
      end if;
    end loop;
  end if;

  update public.research_jobs set
    status = case when value.cancel_requested_at is not null then 'cancelled'::public.research_job_status else p_status end,
    result = coalesce(p_result, '{}'::jsonb) || jsonb_build_object('snapshot_updated', snapshot_updated, 'scope', p_scope),
    usage = coalesce(p_usage, '{}'::jsonb), cost_used = greatest(0, coalesce(p_cost_used, 0)),
    completed_at = clock_timestamp(), lease_expires_at = null, lease_owner = null, lease_token = null
   where id = value.id returning * into value;
  insert into public.research_job_events(job_id, event_type, payload)
    values (value.id, value.status::text, jsonb_build_object('usage', value.usage, 'cost_used', value.cost_used, 'snapshot_updated', snapshot_updated));
  return next value;
end; $$;

revoke all on function public.fieldnote_commit_incremental_research_job(text, uuid, public.research_job_status, jsonb, jsonb, numeric, jsonb, jsonb) from public;
grant execute on function public.fieldnote_commit_incremental_research_job(text, uuid, public.research_job_status, jsonb, jsonb, numeric, jsonb, jsonb) to service_role;
