# FIELDNOTE P0 - raport wdrożenia

Data: 2026-07-16  
Zakres: wyłącznie P0.1-P0.4 z `FIELDNOTE_REPAIR_PLAN.md`.

## Zakres ukończony

### 1. Koordynator runów i blokady

- Dodano trwały koordynator w `fieldnote-api/run_coordinator.py`.
- Każdy run otrzymuje niezmienny `context.json` w `fieldnote-api/runs/work/<run_id>/`.
- Context zawiera identyfikator runu, produkt, `group_key`, markę, model, marketplace, wybrane oferty, ścieżki lokalnych snapshotów, flagi, znaczniki czasu oraz wersję pipeline'u.
- Lock `output/run_locks/product-<product_slug>.lock` gwarantuje, że dla jednego produktu działa tylko jeden run. Kolejny request otrzymuje HTTP 409.
- Różne produkty nadal mogą działać równolegle.
- Globalne operacje agregujące korzystają z osobnego locka `output/run_locks/aggregation.lock`.
- Wybrane oferty są materializowane do katalogu roboczego runu; wspólny `new_offers.csv` nie jest już aktywnym kontekstem uruchomienia.

### 2. Timeout, anulowanie i recovery

- Centralna konfiguracja limitów etapów znajduje się w `scripts/p0_runtime.py`.
- Manifest runu utrwala: `status`, `current_step`, `child_pid`, `last_heartbeat_at`, `lease_expires_at`, `started_at` i `finished_at`.
- Obsługiwane statusy: `queued`, `running`, `succeeded`, `failed`, `timed_out`, `cancelled`, `interrupted`.
- Dodano `POST /api/runs/{run_id}/cancel`; anulowanie zatrzymuje wyłącznie grupę procesów potomnych należącą do danego runu.
- Przy starcie API osierocone manifesty `queued`/`running`, których PID już nie działa, są zmieniane na `interrupted`. Logi i możliwość retry pozostają zachowane.
- Anulowanie jest rozróżniane od błędu także dla analizy i odświeżania opartych o zapisane snapshoty.

### 3. Atomowe zapisy i zachowanie poprzedniego wyniku

- Dodano wspólne prymitywy atomowego zapisu do `scripts/p0_runtime.py`.
- Zapis przebiega przez staging, flush i `fsync`, walidację, atomic rename oraz kopię `.previous` poprzedniej poprawnej wersji.
- Cleaner zapisuje pochodne artefakty jako bundle: `technical_clean.md`, `offer_sections.json`, `product_images.json`, `seller_info.json` i podsumowanie.
- Atomowy zapis obejmuje także `group.json`, `model_state.json`, benchmark, coverage, snapshot frontendu, manifesty runów i kanoniczny stan produktu.
- Przerwanie zapisu przed commit nie zastępuje poprzednich poprawnych `group.json` ani `model_state.json`.

### 4. Kanoniczny status produktu

- Dodano `output/product_state.json` jako jedyne źródło stanu wykonawczego produktu.
- Każdy rekord ma kontrakt:

```json
{
  "product_slug": "",
  "result_status": "none|ready|invalid",
  "active_run_status": "none|queued|running",
  "last_successful_run_id": null,
  "last_failed_run_id": null,
  "last_successful_at": null,
  "last_failed_at": null,
  "refresh_recommended": false,
  "refresh_reason": null,
  "updated_at": ""
}
```

- Publiczny status stosuje pierwszeństwo wyniku: aktywny run z wcześniejszym wynikiem daje `analysis_running`; późniejsza porażka przy istniejącym wyniku daje `refresh_recommended`; błąd bez poprawnego wyniku daje `analysis_failed`.
- Eksporter snapshotu frontendu czyta kanoniczny stan z zachowaniem kompatybilności dla starszych danych.
- Jednorazowy skrypt `scripts/bootstrap_product_state.py` utworzył stan dla istniejącego katalogu bez zmiany merytorycznej zawartości `model_state.json`.

## Zmienione pliki

- `scripts/p0_runtime.py`
- `fieldnote-api/run_coordinator.py`
- `fieldnote-api/app.py`
- `scripts/run_model_research_pipeline.py`
- `scripts/clean_offer_pages_technical.py`
- `scripts/build_model_groups.py`
- `scripts/extract_model_facts_cascade.py`
- `scripts/build_model_benchmark.py`
- `scripts/report_model_coverage.py`
- `scripts/export_frontend_snapshot.py`
- `scripts/bootstrap_product_state.py`
- `scripts/check_p0_foundation.py`
- `fieldnote-frontend/src/app/App.tsx`

## Weryfikacja

Test izolowany `scripts/check_p0_foundation.py` sprawdza:

1. konflikt dwóch równoległych runów tego samego produktu, w tym HTTP 409;
2. równoległe locki dla różnych produktów oraz globalny lock agregacji;
3. timeout subprocessu sterowany centralną konfiguracją;
4. immutable context i lokalną selekcję ofert bez nadpisania wspólnego pliku;
5. anulowanie procesu potomnego;
6. recovery osieroconego runu wywoływane tą samą ścieżką co przy starcie API;
7. przerwanie bundle zapisu `group.json` i `model_state.json`;
8. poprawny wynik, po którym następuje failed run;
9. failed run bez poprawnego wyniku;
10. aktywny refresh przy zachowanym poprawnym wyniku.

Wynik testu: `Result: OK`.

Bez sieci uruchomiono także fixture pipeline'u `success` oraz produkcyjny build Vite. Nie wywołano Firecrawl ani OpenAI.

## Pozostałe granice P0

- Locki są przeznaczone dla jednej lokalnej instancji API i lokalnego systemu plików; nie są rozproszonym mechanizmem dla wielu hostów.
- Transakcja obejmuje pojedyncze artefakty i cleaner bundle. Pełny przebieg pipeline'u nadal jest sekwencją odrębnych, atomowych commitów, a nie jedną globalną transakcją całego benchmarku.
- `npm run build` przechodzi. Istniejące, niezależne błędy `npm run typecheck` w konfiguracji TypeScript nie były rozszerzane w P0.

## Status P0

`P0_COMPLETE`

P1 nie został rozpoczęty.
