-- Development seed: idempotent catalog and schema metadata only. Auth users are
-- deliberately not seeded because production accounts are created by an admin.
insert into public.brands (brand_key, display_name)
values ('lionelo', 'Lionelo')
on conflict (brand_key) do update set display_name = excluded.display_name;

insert into public.products (product_id, brand_id, brand, model, configuration, product_slug, group_key, category_key, benchmark_group_key, status, is_lionelo)
select 'product:lionelo:seed-stroller:', id, 'Lionelo', 'Seed Stroller', '', 'lionelo__seed-stroller', 'lionelo|seed stroller', 'strollers', 'strollers', 'draft', true
from public.brands where brand_key = 'lionelo'
on conflict (product_id) do update set updated_at = now();

insert into public.attribute_schema_versions (version, category_key, definition, is_active)
values ('stroller-v1', 'strollers', '{"attributes": []}'::jsonb, true)
on conflict (version) do update set definition = excluded.definition;
