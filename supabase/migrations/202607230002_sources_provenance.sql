create type public.source_type as enum ('manufacturer', 'marketplace_offer', 'retailer', 'review', 'social', 'other');

create table public.sources (
  id uuid primary key default gen_random_uuid(),
  source_id text not null unique,
  source_type public.source_type not null default 'other',
  marketplace text,
  offer_id text,
  canonical_url text,
  original_url text,
  domain text,
  content_hash text,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  retired_at timestamptz
);

create unique index sources_marketplace_offer_unique
  on public.sources(marketplace, offer_id) where offer_id is not null;

create table public.product_source_links (
  id uuid primary key default gen_random_uuid(),
  link_id text not null unique,
  product_id text not null references public.products(product_id) on delete cascade,
  source_id text not null references public.sources(source_id) on delete restrict,
  group_key text not null default '',
  role text not null default 'supplementary',
  created_at timestamptz not null default now(),
  unique (product_id, source_id)
);

create table public.content_families (
  id uuid primary key default gen_random_uuid(),
  family_key text not null unique,
  label text not null,
  created_at timestamptz not null default now()
);

create table public.source_snapshots (
  id uuid primary key default gen_random_uuid(),
  source_id text not null references public.sources(source_id) on delete restrict,
  content_hash text not null,
  raw_object_path text,
  clean_object_path text,
  fetched_at timestamptz not null default now(),
  http_status integer,
  metadata jsonb not null default '{}'::jsonb,
  unique (source_id, content_hash)
);

create table public.evidence_items (
  id uuid primary key default gen_random_uuid(),
  evidence_id text not null unique,
  product_id text not null references public.products(product_id) on delete cascade,
  source_id text references public.sources(source_id) on delete restrict,
  product_source_link_id text references public.product_source_links(link_id) on delete set null,
  field_name text not null,
  normalized_field_name text not null,
  value text,
  normalized_value text,
  excerpt text not null default '',
  evidence_status text not null,
  validation_status text not null default '',
  confidence text not null default 'unknown',
  content_family_id uuid references public.content_families(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.fieldnote_validate_evidence_link()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  linked_product_id text;
  linked_source_id text;
begin
  if new.product_source_link_id is null then
    return new;
  end if;

  select product_id, source_id
    into linked_product_id, linked_source_id
    from public.product_source_links
   where link_id = new.product_source_link_id;

  if not found
     or new.product_id is distinct from linked_product_id
     or new.source_id is distinct from linked_source_id then
    raise exception 'evidence product, source and product_source_link must agree'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

create trigger fieldnote_validate_evidence_link
before insert or update of product_id, source_id, product_source_link_id
on public.evidence_items
for each row execute function public.fieldnote_validate_evidence_link();

create table public.attribute_values (
  id uuid primary key default gen_random_uuid(),
  product_id text not null references public.products(product_id) on delete cascade,
  schema_version_id uuid not null references public.attribute_schema_versions(id) on delete restrict,
  field_name text not null,
  value jsonb,
  completeness numeric(5,2),
  primary_evidence_id text references public.evidence_items(evidence_id) on delete set null,
  updated_at timestamptz not null default now(),
  unique (product_id, schema_version_id, field_name)
);

create table public.attribute_value_candidates (
  id uuid primary key default gen_random_uuid(),
  attribute_value_id uuid not null references public.attribute_values(id) on delete cascade,
  evidence_id text references public.evidence_items(evidence_id) on delete set null,
  value jsonb,
  candidate_status text not null,
  created_at timestamptz not null default now(),
  unique (attribute_value_id, evidence_id)
);
