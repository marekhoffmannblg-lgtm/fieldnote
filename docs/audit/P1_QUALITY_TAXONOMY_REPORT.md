# FIELDNOTE P1 - quality gate i taksonomia benchmarku

Data: 2026-07-16  
Zakres: wyłącznie P1.5 i P1.6 z `FIELDNOTE_REPAIR_PLAN.md`.

## Wdrożenie

### Deterministyczny quality gate

- Dodano `scripts/quality_gate.py`, wykonywany przed zapisem `model_state.json` w kaskadzie oraz w offline rewalidacji.
- Każde pole otrzymuje `validation_status` (`valid`, `weak`, `conflicting`, `rejected`, `unattributed_legacy`) oraz metadane jakości: nazwa pola, znormalizowana wartość, źródło, fragment evidence, status evidence, confidence i `content_family_id`.
- Gate odrzuca evidence z frazami typu „brak informacji”, claims dla innego parametru lub modelu, kolor jako materiał ramy, ogólne składanie jako składanie jedną ręką oraz opcjonalne zakupy jako akcesoria zestawu.
- Klony w jednej `content_family_id` nie tworzą niezależnego konfliktu.
- `weak` jest liczone jako połowa pola w coverage; `valid` jako pełne pole. `rejected` i `unattributed_legacy` nie podnoszą coverage.
- Raporty odrzuceń zapisano w `output/quality_gate/<product_slug>.json`.

### Offline rewalidacja

- Dodano `scripts/revalidate_final_states.py`.
- Rewalidacja objęła kolejno pięć istniejących finalnych stanów i korzystała wyłącznie z lokalnych stanów, registry, group metadata oraz zapisanych snapshotów.
- Przed zmianą każdy `model_state.json` otrzymał wersję historyczną w `output/model_groups/<slug>/history/*__p1_quality_gate/`.
- Przebudowano benchmark, coverage i snapshot frontendu bez Allegro search, Firecrawl, Playwright, OpenAI ani źródeł producentów.

### Taksonomia

- Dodano wersjonowaną taksonomię `v1` w `scripts/benchmark_taxonomy.py`.
- Katalog i `group.json` mają jawne: `category`, `subcategory`, `benchmark_category`, `taxonomy_version`, `taxonomy_status` i powód klasyfikacji.
- Klasyfikacja korzysta z lokalnych tytułów źródeł. Pełne opisy listingów nie są używane, ponieważ zawierają rekomendowane produkty i mogłyby fałszywie zmieniać kategorię.
- Brak `benchmark_category` lub `taxonomy_status=review_required` blokuje udział w benchmarku, ale nie usuwa produktu.
- Endpoint benchmarku dopuszcza wyłącznie produkty z identycznym `benchmark_category` oraz `taxonomy_version`.

## Rewalidowane produkty

| product_slug | fields_before | fields_valid | fields_weak | fields_conflicting | fields_rejected | coverage_before | coverage_after | benchmark_category_before | benchmark_category_after | taxonomy_status | final_status |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|
| cybex__orfeo | 13 | 9 | 0 | 0 | 4 | 61.90% | 42.86% | Spacerówki lekkie | Lekkie spacerówki podróżne | classified | ready |
| kinderkraft__moov | 10 | 7 | 0 | 0 | 3 | 47.62% | 33.33% | Spacerówki lekkie | Wózki wielofunkcyjne | classified | ready |
| kinderkraft__nebo | 12 | 7 | 0 | 0 | 3 | 52.38% | 33.33% | Spacerówki lekkie | Lekkie spacerówki podróżne | classified | ready |
| kinderkraft__tik | 12 | 11 | 0 | 0 | 1 | 57.14% | 52.38% | Spacerówki lekkie | Klasyczne spacerówki | classified | ready |
| kinderkraft__trig-3 | 13 | 6 | 0 | 0 | 7 | 61.90% | 28.57% | Spacerówki lekkie | Klasyczne spacerówki | classified | ready |

## Naprawione przypadki

- **CYBEX ORFEO:** `Rama=czarna` oraz wariant Taupe zostały odrzucone jako materiały ramy; dowód marki zawierający „brak bezpośredniego potwierdzenia” nie jest potwierdzeniem; zakupy „za dopłatą” nie są akcesoriami zestawu.
- **Kinderkraft NEBO:** witness „Brak szczegółowych informacji o siedzisku” nie tworzy konfliktu i nie potwierdza siedziska.
- **Kinderkraft MOOV:** „Możliwość złożenia: Tak” nie potwierdza pola „Składanie jedną ręką”. MOOV jest w kategorii `Wózki wielofunkcyjne`, poza lekkimi spacerówkami.

## Podsumowanie

- `products_revalidated`: 5
- `fields_rejected_total`: 18
- `legacy_evidence_found`: 10
- `conflicts_found`: 0
- `coverage_changed_products`: 5
- `taxonomy_migrated_products`: 14
- `taxonomy_review_required`: 1 (`kinderkraft|yoxi`)
- `moov_category_fixed`: true
- `benchmark_rebuilt`: true
- `network_fetches`: 0
- `openai_calls`: 0
- `tests_added`: `scripts/check_p1_quality_taxonomy.py` (10 scenariuszy offline)
- `tests_passed`: true
- `frontend_build`: passed
- `typecheck_status`: failed - 3 istniejące błędy TypeScript w `fieldnote-frontend/src/app/App.tsx` (`TS2367` oraz dwa użycia `.at()` poza aktualnym targetem). Nie są częścią P1.5/P1.6 i nie były zmieniane.

## Zmienione pliki

- `scripts/quality_gate.py`
- `scripts/revalidate_final_states.py`
- `scripts/benchmark_taxonomy.py`
- `scripts/migrate_benchmark_taxonomy.py`
- `scripts/check_p1_quality_taxonomy.py`
- `scripts/catalog_registry.py`
- `scripts/build_model_groups.py`
- `scripts/extract_model_facts_cascade.py`
- `scripts/build_model_benchmark.py`
- `scripts/report_model_coverage.py`
- `scripts/export_frontend_snapshot.py`
- `fieldnote-api/app.py`
- `data/catalog/categories.json`
- `data/catalog/products.json`
- `output/model_groups/*/group.json`
- `output/model_groups/*/model_state.json` (tylko przez rewalidację z backupem)
- `output/quality_gate/*.json`
- `output/model_benchmark.csv`
- `output/model_coverage.csv`
- `fieldnote-frontend/src/data/generated/`

`Result: P1_QUALITY_TAXONOMY_COMPLETE`

P2 i kolejne zakresy nie zostały rozpoczęte.
