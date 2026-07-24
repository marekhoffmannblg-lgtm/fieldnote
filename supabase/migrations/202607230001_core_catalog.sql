create extension if not exists pgcrypto;

create type public.fieldnote_role as enum ('viewer', 'analyst', 'admin');
create type public.product_status as enum ('active', 'eol', 'draft', 'archived');

create table public.brands (
  id uuid primary key default gen_random_uuid(),
  brand_key text not null unique,
  display_name text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.products (
  id uuid primary key default gen_random_uuid(),
  product_id text not null unique,
  brand_id uuid not null references public.brands(id),
  brand text not null,
  model text not null,
  configuration text not null default '',
  product_slug text not null unique,
  group_key text not null unique,
  category_key text not null default '',
  benchmark_group_key text not null default '',
  status public.product_status not null default 'draft',
  is_lionelo boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (brand, model, configuration)
);

create table public.product_aliases (
  id uuid primary key default gen_random_uuid(),
  product_id text not null references public.products(product_id) on delete cascade,
  alias text not null,
  normalized_alias text not null,
  alias_kind text not null default 'model',
  created_at timestamptz not null default now(),
  unique (product_id, normalized_alias)
);

create table public.product_skus (
  id uuid primary key default gen_random_uuid(),
  product_id text not null references public.products(product_id) on delete cascade,
  sku text not null,
  market text not null default 'PL',
  created_at timestamptz not null default now(),
  unique (product_id, sku, market)
);

create table public.attribute_schema_versions (
  id uuid primary key default gen_random_uuid(),
  version text not null unique,
  category_key text not null,
  definition jsonb not null,
  is_active boolean not null default false,
  created_at timestamptz not null default now()
);

create unique index attribute_schema_one_active_per_category
  on public.attribute_schema_versions(category_key) where is_active;

create table public.product_profile_overrides (
  id uuid primary key default gen_random_uuid(),
  product_id text not null references public.products(product_id) on delete cascade,
  field_name text not null,
  value jsonb not null,
  reason text not null,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  superseded_at timestamptz,
  unique (product_id, field_name, created_at)
);
