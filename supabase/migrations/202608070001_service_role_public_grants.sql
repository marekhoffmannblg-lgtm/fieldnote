-- FastAPI uses the server-side service_role key. Keep these privileges separate
-- from authenticated grants and leave RLS policies unchanged.
grant usage on schema public to service_role;

do $$
declare
  relation_name text;
begin
  for relation_name in
    select tablename
    from pg_catalog.pg_tables
    where schemaname = 'public'
  loop
    execute format(
      'grant select, insert, update, delete on table public.%I to service_role',
      relation_name
    );
  end loop;

  for relation_name in
    select sequence_name
    from information_schema.sequences
    where sequence_schema = 'public'
  loop
    execute format(
      'grant usage, select, update on sequence public.%I to service_role',
      relation_name
    );
  end loop;
end
$$;
