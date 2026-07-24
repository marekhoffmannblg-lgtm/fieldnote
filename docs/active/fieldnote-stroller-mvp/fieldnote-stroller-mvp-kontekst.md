# FIELDNOTE Stroller MVP — kontekst

- **Branch:** `main` (preflight Unit 2: czyste drzewo i synchronizacja z `origin/main`)
- **Ostatni commit przed Unit 2:** `807e81bd9176e274925ce3d1feac67fdb3dc9447 — data: add lionelo internal specification fixtures`
- **Ostatnia aktualizacja:** 2026-07-24

## Źródła

- Requirements: `docs/brainstorms/2026-07-23-fieldnote-stroller-mvp-requirements.md`
- Plan techniczny: `docs/plans/2026-07-23-001-feat-fieldnote-stroller-mvp-plan.md`

## Obecny stan repozytorium

- Przed rozpoczęciem Unit 2 drzewo robocze było czyste, a `main` oraz `origin/main` wskazywały commit `807e81b`.
- Istnieje lokalny pipeline Python, FastAPI, frontend React/Vite, provenance, quality gate, retry i historia runów. Kanoniczny entrypoint researchu pozostaje `scripts/run_model_research_pipeline.py`.
- Repozytoryjny starter Codex v2 jest zainstalowany. Wprowadza workflow `dev-docs`; jego konfiguracja nie wykonuje pracy aplikacyjnej podczas tej inicjalizacji.
- Aktywne zadanie jest zapisane w osobnym commicie. Drzewo pozostaje brudne, dlatego Unit 1 stage'uje wyłącznie własne pliki i pojedynczy hunk hygiene w `scripts/check_fieldnote.sh`.

## Potwierdzone wzorce i ważne pliki

- `scripts/source_adapters.py`: adaptery tylko odkrywają/normalizują źródła; lifecycle nie należy do adaptera.
- `scripts/provenance_v1.py`, `scripts/source_commit.py`, `scripts/source_lifecycle.py`, `scripts/quality_gate.py`: zachować evidence, provenance i semantykę `partial`.
- `fieldnote-api/run_coordinator.py` i `scripts/p0_runtime.py`: bieżące wzorce locków, lease i atomowych zapisów do zachowania jako characterization coverage.
- `scripts/catalog_registry.py`, `scripts/import_lionelo_strollers.py`, `scripts/import_lionelo_internal_specs.py`: katalog oraz import danych Lionelo.
- `fieldnote-api/app.py` i `fieldnote-frontend/src/app/App.tsx`: istniejące surface API/UI; refaktoryzować tylko wraz z konkretnym przenoszonym ekranem.
- `scripts/check_fieldnote.sh`: kanoniczna offline bramka.

## Decyzje

- Supabase jest docelowym systemem trwałym dla PostgreSQL, Auth i Storage; frontend używa go wyłącznie do sesji, a dane biznesowe przechodzą przez FastAPI.
- Pipeline jest opakowywany i migrowany przyrostowo, nie przepisywany od zera.
- Benchmark jest zawsze dla jednostki `model + konfiguracja`; cena jest odrębna od rankingu użytkowego; brak danych obniża kompletność, a nie daje zera.
- MVP obejmuje wyłącznie polski rynek wózków, 34 produkty Lionelo i obecnych realnych konkurentów.

## Designerski kontekst

- Źródło prawdy: `docs/UX_REDESIGN.md` (istnieje).
- Figma: brak (`figma_spec: null`, `figma_screens: {}`).
- Nie wykonywać pełnego redesignu; utrzymać istniejące URL-e i język wizualny przy migracji ekranów.

## Wyniki wykonania i testów

- Unit 1 dodał przykładowe pliki środowiskowe, repo hygiene test, CI, Dependabot i security baseline. Pliki lokalnych env, wejść, outputów, runów i artefaktów są ignorowane; istniejące lokalne pliki nie zostały usunięte.
- `python3 -m unittest tests/test_repository_hygiene.py`: PASS (2 testy).
- `bash scripts/check_fieldnote.sh`: PASS. Backend unit/integration/fixture tests, checkery P0/P1, dry-run provenance i frontend typecheck/test/build przeszły bez Firecrawl/OpenAI.
- Build Vite zgłosił nieblokujące ostrzeżenie o chunku większym niż 500 kB; nie jest to część Unit 1.
- Review Unit 1 (`298f40b..c75a0c8`): correctness_reviewer, security_reviewer i test_reviewer niezależnie sprawdzili zakres; UI/data review nie były wymagane. Ponowione `python3 -m unittest tests/test_repository_hygiene.py` i `bash scripts/check_fieldnote.sh` przeszły.
- Gate review: **WYMAGA POPRAWEK** — 0 P1, 2 P2, 0 P3. P2: CI nie instaluje zależności `fieldnote-api` na czystym runnerze; hygiene test czyta worktree zamiast staged blobu. Raport: `review-unit-1.md`.
- Naprawa P2: `.github/workflows/ci.yml` instaluje także `fieldnote-api/requirements.txt`; `tests/test_repository_hygiene.py` czyta staged blob przez `git show :<path>`. Dodano regresje dla staged sekretu z bezpiecznym worktree oraz kontrakt CI dla zależności API.
- Po naprawie: `python3 -m unittest tests/test_repository_hygiene.py` PASS (4 testy), `bash scripts/check_fieldnote.sh` PASS bez Firecrawl/OpenAI. Oczekuje ograniczony re-review wyłącznie tych zmian.
- Ograniczony re-review `c75a0c8..a5454f4`: correctness i security PASS, test reviewer wykrył nowy P2. Po commicie staged fixture z literalnym `sk-...` jest skanowany jako sekret, więc `python3 -m unittest tests/test_repository_hygiene.py` FAIL (1/4). Poprzednie P2 są zamknięte; gate pozostaje **WYMAGA POPRAWEK** (0 P1, 1 P2, 0 P3).
- Finalna naprawa P2 buduje fixture tokenu z fragmentów, więc śledzony plik testu nie zawiera sekretopodobnego literalu, a staged fixture nadal jest wykrywany w tymczasowym repo. `python3 -m unittest tests/test_repository_hygiene.py` PASS (4), `bash scripts/check_fieldnote.sh` PASS. Ograniczony re-review przez correctness_reviewer, security_reviewer i test_reviewer: PASS; gate **GOTOWE DO KONTYNUACJI** (0 P1, 0 P2, 0 P3).
- Unit 1.5: zapisano `repository-cleanup-plan.md` po odczytowym audycie rootu. Usunięto wyłącznie odtwarzalne cache/local env (`.venv`, API venv, pnpm/Vite cache, oba node_modules, dist, pycache i `.DS_Store`), a 31 ZIP-ów diagnostycznych przeniesiono do `archive/repository-cleanup/2026-07-24/`. `project_files.txt` przeniesiono do tracked archive. Nie ruszono kodu ani kanonicznych ścieżek danych.
- Przed cleanupem `bash scripts/check_fieldnote.sh` PASS. Po cleanupie `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_repository_hygiene.py` PASS (4); lokalne uruchomienie API/UI wymaga ponownej instalacji zależności.
- Unit 2 dodał wersjonowany baseline Supabase: `config.toml`, pięć uporządkowanych migracji (katalog, provenance, rynek/benchmarki, joby/audyt oraz Auth/RLS/Storage), idempotentne seedy dev/E2E i offline kontrakty schematu oraz polityk. Zachowano stabilne tekstowe `product_id`, `source_id` i `evidence_id`; częściowy indeks blokuje drugi aktywny job produktu; źródło może łączyć się z wieloma produktami.
- RLS obejmuje wszystkie 26 tabel biznesowych. Self-signup i anonymous sign-in są wyłączone; anon nie otrzymuje polityk, viewer ma wyłącznie odczyt, analyst/admin zapis danych, a zarządzanie profilami i katalogiem pozostaje adminowi. Buckety `source-raw`, `source-clean` i `imports` są prywatne; dostęp do obiektów ma wyłącznie analyst/admin.
- `fieldnote-api/.venv/bin/python -m unittest tests/test_supabase_schema_contract.py tests/test_rls_policy_contract.py`: PASS (7 testów).
- `bash scripts/check_fieldnote.sh`: PASS; pełny offline gate wraz z API i frontendem przeszedł bez wywołań Firecrawl/OpenAI.

## Blokery i ryzyka

- Lokalny runtime nie ma Supabase CLI, Dockera ani `psql`; nie zweryfikowano wykonania migracji przez `supabase db reset`. Nie instalowano narzędzi ani nie wykonywano destrukcyjnego resetu. Ten krok pozostaje warunkiem domknięcia weryfikacji Unit 2.
- Istniejące lokalne dane, outputy i środowiska nie mogą trafić do repo.
- Live provider calls i koszty są poza automatyczną weryfikacją.

## Przekazanie

- **Bieżący unit:** Unit 2 — Supabase schema, Auth, Storage i RLS
- **Status:** partial — implementacja i offline kontrakty są zielone, ale brakuje lokalnego runtime Supabase do potwierdzenia czystego `db reset`.
- **Pliki w toku:** `supabase/`, `e2e/seeds/fieldnote-stroller-mvp-seed.sql`, kontrakty Unit 2 i aktywne dokumenty zadania.
- **Ostatnie testy:** 7 testów kontraktowych Unit 2 PASS; pełny offline gate PASS.
- **Bloker:** Supabase CLI/Docker/PostgreSQL nie są dostępne lokalnie; potrzebne jest niedestrukcyjne środowisko Supabase do `supabase db reset` i wykonawczych testów RLS.
- **Następny krok:** uruchomić wyłącznie weryfikację runtime Unit 2 w przygotowanym środowisku, następnie `$dev-docs-review docs/active/fieldnote-stroller-mvp 2`; nie rozpoczynać Unit 3.
