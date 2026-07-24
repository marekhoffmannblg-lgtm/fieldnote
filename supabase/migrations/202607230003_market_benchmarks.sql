create table public.sellers (
  id uuid primary key default gen_random_uuid(),
  seller_key text not null unique,
  display_name text not null,
  created_at timestamptz not null default now()
);

create table public.offers (
  id uuid primary key default gen_random_uuid(),
  source_id text not null unique references public.sources(source_id) on delete restrict,
  product_id text references public.products(product_id) on delete set null,
  seller_id uuid references public.sellers(id) on delete set null,
  currency text not null default 'PLN',
  created_at timestamptz not null default now()
);

create table public.price_observations (
  id uuid primary key default gen_random_uuid(),
  offer_id uuid not null references public.offers(id) on delete cascade,
  gross_price numeric(12,2) not null check (gross_price >= 0),
  observed_at timestamptz not null default now(),
  available boolean,
  unique (offer_id, observed_at)
);

create table public.availability_observations (
  id uuid primary key default gen_random_uuid(),
  offer_id uuid not null references public.offers(id) on delete cascade,
  available boolean not null,
  observed_at timestamptz not null default now(),
  unique (offer_id, observed_at)
);

create table public.competitive_benchmarks (
  id uuid primary key default gen_random_uuid(),
  benchmark_id text not null unique,
  benchmark_group_key text not null,
  anchor_product_id text not null references public.products(product_id) on delete restrict,
  title text not null,
  status text not null default 'draft',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.competitive_benchmark_participants (
  benchmark_id uuid not null references public.competitive_benchmarks(id) on delete cascade,
  product_id text not null references public.products(product_id) on delete restrict,
  position integer not null default 0,
  primary key (benchmark_id, product_id)
);

create table public.benchmark_results (
  id uuid primary key default gen_random_uuid(),
  benchmark_id uuid not null references public.competitive_benchmarks(id) on delete cascade,
  product_id text not null references public.products(product_id) on delete restrict,
  profile_key text not null,
  utility_score numeric(8,3),
  price_summary jsonb,
  completeness numeric(5,2),
  computed_at timestamptz not null default now(),
  unique (benchmark_id, product_id, profile_key)
);

create table public.benchmark_snapshots (
  id uuid primary key default gen_random_uuid(),
  benchmark_id uuid not null references public.competitive_benchmarks(id) on delete cascade,
  semantic_hash text not null,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  unique (benchmark_id, semantic_hash)
);
