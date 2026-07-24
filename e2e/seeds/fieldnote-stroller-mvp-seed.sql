-- E2E fixtures are deliberately separate from Supabase's development seed.
-- Re-running this file is safe and does not create Auth users or credentials.
insert into public.brands (brand_key, display_name)
values ('fixture-brand', 'Fixture Brand')
on conflict (brand_key) do update set display_name = excluded.display_name;

insert into public.products (product_id, brand_id, brand, model, configuration, product_slug, group_key, category_key, benchmark_group_key, status, is_lionelo)
select 'product:fixture:stroller:', id, 'Fixture Brand', 'Stroller', '', 'fixture-brand__stroller', 'fixture brand|stroller', 'strollers', 'strollers', 'active', false
from public.brands where brand_key = 'fixture-brand'
on conflict (product_id) do update set updated_at = now();
