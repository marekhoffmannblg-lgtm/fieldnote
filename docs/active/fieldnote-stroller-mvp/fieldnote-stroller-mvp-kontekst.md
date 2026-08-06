# FIELDNOTE Stroller MVP — kontekst

- **Branch:** `main` (preflight Unit 2: czyste drzewo i synchronizacja z `origin/main`)
- **Ostatni commit przed Unit 2:** `807e81bd9176e274925ce3d1feac67fdb3dc9447 — data: add lionelo internal specification fixtures`
- **Ostatnia aktualizacja:** 2026-07-30

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
- Review Unit 2 (`807e81b..53af30a`) objął `correctness_reviewer`, `security_reviewer`, `test_reviewer` i wymagany `data_reviewer`. Ponowione kontrakty Supabase/RLS (7/7), pełny offline gate i `git diff --check` przeszły; executor potwierdził także `supabase start` oraz `supabase db reset` jako PASS.
- Gate Unit 2: **WYMAGA POPRAWEK** — 0 P1, 4 P2, 0 P3. Zaakceptowano: spoofing `audit_events.actor_id`, niespójny link evidence/provenance, brak wykonawczych testów RLS/Storage oraz brak wykonawczego testu idempotencji obu seedów. Raport: `review-unit-2.md`.
- Naprawa czterech P2 Unit 2: trigger `fieldnote_set_audit_actor` odrzuca cudzy `actor_id` i przypisuje subject JWT; trigger `fieldnote_validate_evidence_link` odrzuca niespójny product/source/link. Dodano opt-in test wykonawczy `tests/test_supabase_runtime_contract.py`; korzysta wyłącznie z lokalnego `supabase db query`, krótkotrwałych testowych użytkowników i JWT podpisanych lokalnym sekretem pobranym w pamięci przez CLI, bez sekretów w repozytorium.
- Po poprawkach `supabase db reset --local --yes` PASS; `FIELDNOTE_SUPABASE_INTEGRATION=1 fieldnote-api/.venv/bin/python -m unittest tests/test_supabase_runtime_contract.py` PASS (4). Kontrakty schema/RLS przechodzą (9 testów), pełny `bash scripts/check_fieldnote.sh` PASS, `git diff --check` PASS.
- Ograniczony re-review `53af30a..c436472` przez correctness, security, tests i data: spoofing aktora audytu jest zamknięty, ale gate pozostaje **WYMAGA POPRAWEK** (0 P1, 3 P2, 0 P3). P2: update użytego linku rozjeżdża evidence, runtime test nie wykonuje RLS tabel przez anon/API, test seedów nie porównuje stabilnych UUID. Raport: `review-unit-2.md`.
- Re-review uruchomił kontrakty schema/RLS (9 PASS), runtime contract (4 PASS) oraz `git diff --check 53af30a..c436472` (PASS). Nie wykonano Unit 3.
- Naprawiono trzy pozostałe P2 z re-review: trigger `fieldnote_prevent_link_provenance_rewrite` blokuje zmianę produktu lub źródła linku, gdy wskazuje go evidence; test wykonawczy wysyła requesty PostgREST dla anon/viewer/analyst/admin; seed test porównuje UUID brandów i produktów dev/E2E po drugim uruchomieniu. Dla PostgREST dodano niezbędne granty roli `authenticated`; RLS pozostaje granicą autoryzacji, a `anon` nie ma grantów tabel.
- Po naprawach `supabase db reset --local --yes` PASS; runtime contract PASS (5 testów); kontrakty schema/RLS i runtime offline PASS (14 testów, 5 opt-in skipped); pełna offline bramka `bash scripts/check_fieldnote.sh` PASS; `git diff --check` PASS.
- Ograniczony re-review `eaa580e^..eaa580e` przez correctness, security, tests i data potwierdził zamknięcie spójności update linku oraz stabilności UUID seedów. Security i data PASS; correctness i tests zgłosiły ten sam P2: runtime PostgREST nie wykonuje adminowego zapisu katalogu objętego odrębną polityką `admin_write`.
- Weryfikacja re-review: kontrakty schema/RLS/runtime 14 PASS (5 opt-in skipped), runtime Supabase 5 PASS, pełna offline bramka PASS i `git diff --check eaa580e^ eaa580e` PASS. Gate Unit 2 pozostaje **WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3.
- Naprawiono ostatni P2: test PostgREST wykonuje teraz odmowę `POST /brands` dla analyst oraz idempotentny UPSERT identycznego fixture przez admina. Wykonano tylko zmianę runtime contractu; nie zmieniano migracji ani nie rozpoczęto Unit 3.
- Po naprawie runtime contract PASS (5 testów), kontrakty schema/RLS/runtime offline PASS (14 testów, 5 opt-in skipped), pełna offline bramka `bash scripts/check_fieldnote.sh` PASS i `git diff --check` PASS. Oczekuje wyłącznie ograniczony re-review tej poprawki.
- Pełny review Unit 3 (`16e9371..e7b7443`) objął correctness_reviewer, security_reviewer, test_reviewer i data_reviewer. Testy Unit 3 (23 PASS), pełna offline bramka (PASS) oraz `git diff --check` (PASS) zostały powtórzone.
- Gate Unit 3: **BLOKUJE** — 1 P1, 4 P2, 0 P3. P1: migrator nie transformuje kanonicznych rekordów Lionelo `scope=production`/`refresh_recommended` do kontraktu `products`, więc nie migruje wymaganych 34 rekordów. P2: Supabase POST zapisuje legacy katalog, detail odczytuje legacy provenance, brak zatwierdzonego fixture/entrypointu oraz audit nie sprawdza dokładnie 34 Lionelo. Raport: `review-unit-3.md`.
- Naprawiono wyłącznie findings Unit 3: migrator mapuje własność Lionelo po marce lub boolu, kanoniczne statusy na enum `products` oraz projekcje source/link/evidence na kolumny DB. Fixture `fixtures/unit3/validated_state_v1.json` zawiera 34 Lionelo w kanonicznym kształcie `scope=production`/`refresh_recommended`, konkurenta, placeholder oraz kontrolowane błędne referencje.
- `POST /api/products` w Supabase używa repozytorium, a detail Supabase omija legacy walidator i provenance. `run_migration` łączy fixture, migrację i audit; CLI wymaga serwerowej konfiguracji tylko przy rzeczywistym zapisie. Audit wymaga dokładnie 34 unikalnych Lionelo.
- Po poprawkach: focused testy Unit 3/API PASS (27), JSON fixture PASS, `git diff --check` PASS oraz pełny `bash scripts/check_fieldnote.sh` PASS. Oczekuje ograniczony re-review wyłącznie P1/P2 Unit 3.
- Ograniczony re-review Unit 3 (`c8ca42c^..c8ca42c`) przez correctness, security, tests i data: focused suite 27 PASS, pełna offline bramka PASS oraz `git diff --check` PASS, ale gate **BLOKUJE** — 2 P1, 1 P2, 0 P3. P1: domyślny fixture zawiera syntetyczne `00..33`; niezautoryzowany POST zapisuje przez service-role i omija RLS. P2: wielowyrazowa marka ma rozbieżny `brand_key`. Raport: `review-unit-3.md`.
- Naprawiono wyłącznie te 2 P1/1 P2: fixture `fixtures/unit3/validated_state_v1.json` zawiera realne `product_id`, model, konfigurację i slug 34 śledzonych `data/internal_specs/lionelo__*.json`; audit porównuje dokładny expected set z fixturem. `POST /api/products` w trybie Supabase zwraca 503 przed odczytem legacy, zapisem DB lub użyciem service-role do czasu Unit 4. `CatalogRepository.brand_key()` normalizuje marki wielowyrazowe jednym formatem.
- Po poprawkach focused Unit 3/API PASS (29), JSON fixture PASS, `git diff --check` PASS oraz pełna offline bramka `bash scripts/check_fieldnote.sh` PASS. Oczekuje ograniczony re-review wyłącznie tych trzech poprawek; Unit 4 nie został rozpoczęty.
- Ograniczony re-review `3d638b7^..3d638b7` przez correctness, security, tests i data: correctness/security/tests PASS, focused suite 29 PASS, pełna offline bramka PASS i `git diff --check` PASS. Data review przyjął P2: CLI przekazuje `expected_lionelo_product_ids` z dowolnego wejściowego payloadu, więc może ominąć kanoniczny set specs. Gate **WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3. Raport: `review-unit-3.md`.
- Naprawiono wyłącznie ten P2: `run_migration()` zawsze używa kanonicznego zbioru z `data/internal_specs`; deklaracja `expected_lionelo_product_ids` fixture'u służy wyłącznie jako kontrakt regresyjny testu. Dodano przypadek 34 syntetycznych ID z własną deklaracją expected, który kończy się `review`.
- Po poprawce focused Unit 3/API PASS (30), pełny `bash scripts/check_fieldnote.sh` PASS oraz `git diff --check` PASS. Oczekuje ograniczony re-review wyłącznie tej poprawki; Unit 4 nie został rozpoczęty.
- Ograniczony re-review `c93ab1f^..c93ab1f` przez correctness, security, tests i data: correctness oraz tests PASS; security i data zgłosiły ten sam P2. `run_migration()` uruchamia upserty przed kanonicznym audytem, więc niezgodny fixture może zanieczyścić docelowe repozytoria, a dopiero potem zwrócić `review`. Focused suite 30 PASS, pełny `bash scripts/check_fieldnote.sh` PASS oraz `git diff --check c93ab1f^..c93ab1f` PASS. Gate Unit 3: **WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3.
- Naprawiono wyłącznie ten P2: `_canonical_preflight()` porównuje eligible Lionelo z `data/internal_specs` przed zapisami. `main()` wykonuje preflight przed tworzeniem klienta/repozytoriów Supabase, a `run_migration()` powtarza go jako kontrakt programistyczny. Niezgodny fixture zwraca `review` z `canonical_lionelo_set_mismatch` i pozostawia fake catalog/source bez wywołań `upsert_*`.
- Po naprawie focused Unit 3/API PASS (30), `py_compile` migratora/audytu PASS, pełna offline bramka `bash scripts/check_fieldnote.sh` PASS oraz `git diff --check` PASS. Oczekuje ograniczony re-review wyłącznie P2 preflightu; Unit 4 nie został rozpoczęty.
- Ograniczony re-review `4dd87e1^..4dd87e1` przez correctness, security, tests i data: correctness, security i data PASS. Tests przyjął P2: regresja pokrywa `run_migration()`, ale nie wywołuje `main(--input ...)` z sentinelami, więc nie dowodzi wykonawczo braku tworzenia klienta/repozytoriów dla niekanonicznego inputu CLI. Focused suite 30 PASS, pełny `bash scripts/check_fieldnote.sh` PASS oraz `git diff --check 4dd87e1^..4dd87e1` PASS. Gate Unit 3: **WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3.
- Naprawiono wyłącznie ten P2: test CLI zapisuje tymczasowy niekanoniczny fixture, uruchamia `main(["--input", path])` i podmienia moduły repozytoriów sentinelami. Potwierdza kod 2, raport `review`, zerowe liczniki oraz brak konstrukcji `SupabaseClient` i repozytoriów.
- Po naprawie focused Unit 3/API PASS (31), `py_compile` migratora/audytu PASS, pełna offline bramka `bash scripts/check_fieldnote.sh` PASS oraz `git diff --check` PASS. Oczekuje ograniczony re-review wyłącznie P2 testu CLI; Unit 4 nie został rozpoczęty.
- Końcowy ograniczony re-review `8ede9d7^..8ede9d7` przez correctness, security, tests i data: wszyscy PASS. Focused suite 31 PASS, pełna offline bramka PASS oraz `git diff --check 8ede9d7^..8ede9d7` PASS. Gate Unit 3: **GOTOWE DO KONTYNUACJI** — 0 P1, 0 P2, 0 P3.
- Końcowy ograniczony re-review `aa9ca91^..aa9ca91` przez correctness, security i tests: wszyscy PASS. Potwierdzono dwa identyczne UPSERT-y admina, pojedynczy rekord przez adminowy GET PostgREST oraz odmowę dla analyst. Data/UI review nie były wymagane, bo diff dotyczył wyłącznie testu runtime.
- Weryfikacja końcowego re-review: runtime Supabase 5 PASS, kontrakty schema/RLS/runtime 14 PASS (5 opt-in skipped), pełna offline bramka PASS i `git diff --check aa9ca91^ aa9ca91` PASS. Gate Unit 2: **GOTOWE DO KONTYNUACJI** — 0 P1, 0 P2, 0 P3.
- Unit 3 dodał repozytoria katalogu, źródeł, benchmarków, jobów i audytu na wstrzykiwalnym kliencie stdlib PostgREST. `FIELDNOTE_DATA_MODE=legacy_readonly` pozostaje domyślny; `supabase` wymaga `SUPABASE_URL` i `SUPABASE_SERVICE_ROLE_KEY`, a brak konfiguracji kończy się fail-closed bez wycieku sekretu.
- Selektywna migracja przyjmuje wyłącznie wersjonowany JSON/fixture. Upsertuje stabilne klucze biznesowe, importuje zaklasyfikowane produkty Lionelo i konkurencję, odrzuca placeholdery, rekordy niezaklasyfikowane oraz błędne linki/evidence do jawnego raportu. Nie odczytuje ani nie wersjonuje lokalnego `data/`/`output/`; snapshoty Storage pozostają poza offline migracją.
- API katalogu w trybie `supabase` korzysta z `CatalogRepository` i nie wywołuje legacy `load_products()` ani wygenerowanych danych frontendu. Bieżące pipeline, zapisy runów oraz legacy adaptery pozostają nienaruszone do kolejnych unitów.
- Testy Unit 3: 23 PASS (`test_fieldnote_api_contracts`, `test_supabase_repositories`, `test_selective_migration`); pełny `bash scripts/check_fieldnote.sh` PASS (backend, checkery i frontend typecheck/test/build); `git diff --check` PASS. Unit 3 oczekuje pełnego review; Unit 4 nie został rozpoczęty.
- Ograniczony re-review `39c5fdd^..39c5fdd` przez correctness, security i tests: correctness/security PASS; tests zgłosił P2. Pierwszy adminowy UPSERT katalogu jest pokryty, ale test nie wykonuje drugiego requestu ani nie sprawdza jednej trwałej pozycji fixture, więc nie dowodzi wykonawczo idempotencji.
- Weryfikacja re-review: runtime Supabase 5 PASS, kontrakty schema/RLS/runtime 14 PASS (5 opt-in skipped), pełna offline bramka PASS i `git diff --check 39c5fdd^ 39c5fdd` PASS. Gate Unit 2 pozostaje **WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3.
- Naprawiono ostatni P2 wyłącznie w runtime contract: admin wykonuje drugi identyczny POST/UPSERT `brands`, a adminowy GET przez PostgREST potwierdza dokładnie jeden rekord `runtime-admin-catalog`. Odmowa dla analyst pozostaje.
- Po naprawie runtime contract PASS (5 testów), kontrakty schema/RLS/runtime offline PASS (14 testów, 5 opt-in skipped), pełna offline bramka `bash scripts/check_fieldnote.sh` PASS i `git diff --check` PASS. Oczekuje wyłącznie ograniczony re-review tej poprawki.

## Blokery i ryzyka

- Runtime Supabase działa; Unit 2 ma PASS i brak otwartych P1/P2.
- Istniejące lokalne dane, outputy i środowiska nie mogą trafić do repo.
- Live provider calls i koszty są poza automatyczną weryfikacją.
- Unit 4: rozpoznano istniejące API/UI i kontrakty RLS. `npm install` nie działał (`Cannot read properties of null (reading 'matches')`), ale zależność została następnie poprawnie dodana przez `pnpm add @supabase/supabase-js` (v2.110.8). Implementacja auth API/UI i testów pozostaje do wykonania w tym samym Unicie; nie wprowadzono obejścia sesji.
- Unit 4: dodano introspekcję Bearer przez Supabase Auth, profile role/must-change, admin users, frontendowy provider/guard i ekrany auth/users. Focused backend 25 PASS, frontend 11 PASS/typecheck/build PASS, pełny `bash scripts/check_fieldnote.sh` PASS oraz `git diff --check` PASS. Unit 5 nie został rozpoczęty.
- Naprawa findings Unit 4: middleware wymusza sesję dla wszystkich `/api/*` w trybie Supabase z wyjątkiem health i auth; `change-password` aktualizuje hasło przez serwerowy Auth Admin przed zdjęciem flagi; focused backend 26 PASS, pełny `bash scripts/check_fieldnote.sh` PASS i `git diff --check` PASS. Oczekuje ograniczony re-review Unit 4; Unit 5 nie został rozpoczęty.
- Naprawiono pozostałe findings Unit 4: centralny middleware odrzuca wszystkie metody mutujące (`POST`, `PUT`, `PATCH`, `DELETE`) dla roli viewer, pozostawiając odczyt dla viewer/analyst/admin; dodano wykonawczą macierz `TestClient` dla anon, wszystkich ról, wymuszonej zmiany hasła oraz odmowy mutacji viewer. Dodano `httpx` jako zależność testową API. Focused backend PASS (27), pełny `bash scripts/check_fieldnote.sh` PASS i `git diff --check` PASS. Oczekuje ograniczony re-review wyłącznie tej poprawki; Unit 5 nie został rozpoczęty.
- Ograniczony re-review Unit 4 (`475e04c^..475e04c`) przez correctness_reviewer, security_reviewer i test_reviewer: security i tests PASS, correctness wykazał P1 potwierdzony przez inspekcję. `AuthProvider.changeInitialPassword()` najpierw zmienia hasło bezpośrednio w Supabase, a następnie wysyła pusty `POST /api/auth/change-password`; router wymaga `password`, więc zwraca 422 i nie zdejmuje `must_change_password`. Gate **BLOKUJE** — 1 P1, 0 P2, 0 P3. Focused API PASS (27), pełny `bash scripts/check_fieldnote.sh` PASS oraz `git diff --check 475e04c^..475e04c` PASS. Unit 5 nie został rozpoczęty.
- Naprawiono wyłącznie P1 Unit 4: frontend nie wywołuje już `supabase.auth.updateUser()`; wysyła `{password}` do serwerowego `POST /api/auth/change-password`, który zachowuje kolejność zmiany hasła i zdjęcia flagi. Nowy deterministyczny test sprawdza payload oraz odświeżenie profilu z `mustChangePassword=true` do `false`. Focused API PASS (27), frontend PASS (12), typecheck PASS, build PASS (istniejące ostrzeżenie chunk >500 kB), pełny `bash scripts/check_fieldnote.sh` PASS i `git diff --check` PASS. Oczekuje ograniczony re-review wyłącznie P1; Unit 5 nie został rozpoczęty.
- Ograniczony re-review P1 Unit 4 (`cd9ba46^..cd9ba46`) przez correctness_reviewer, security_reviewer, test_reviewer i ui_reviewer: correctness, security i UI PASS; test reviewer wykazał P2 potwierdzony przez inspekcję. `passwordChange.ts` odrzuca tylko truthy `must_change_password`, więc `{}` albo `{must_change_password: null}` wywołuje `refreshProfile()` mimo braku jawnego potwierdzenia. Gate **WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3. Frontend PASS (12), typecheck PASS, pełny `bash scripts/check_fieldnote.sh` PASS oraz `git diff --check cd9ba46^..cd9ba46` PASS. Unit 5 nie został rozpoczęty.
- Naprawiono wyłącznie P2 Unit 4: helper wymaga dokładnie `must_change_password === false` przed odświeżeniem profilu. Regresje dowodzą odrzucenia `{}`, `null` i `true` bez wywołania odświeżenia. Frontend PASS (15), typecheck/build PASS (istniejące ostrzeżenie chunk >500 kB), pełny `bash scripts/check_fieldnote.sh` PASS i `git diff --check` PASS. Oczekuje ograniczony re-review wyłącznie P2; Unit 5 nie został rozpoczęty.
- Końcowy ograniczony re-review P2 Unit 4 (`efd5ab5^..efd5ab5`) przez correctness_reviewer, security_reviewer, test_reviewer i ui_reviewer: wszyscy PASS. Helper fail-closed akceptuje wyłącznie literalne `must_change_password=false`; focused test helpera PASS (4), frontend PASS (15), pełny `bash scripts/check_fieldnote.sh` PASS oraz `git diff --check efd5ab5^..efd5ab5` PASS. Gate Unit 4: **GOTOWE DO KONTYNUACJI** — 0 P1, 0 P2, 0 P3. Unit 5 nie został rozpoczęty.
- Unit 5 dodał trwałą kolejkę PostgreSQL: migracja `202607280001_durable_research_queue.sql` przechowuje payload, usage, koszt, anulowanie, heartbeat i fenced lease. Transakcyjny RPC z advisory lockiem, `FOR UPDATE SKIP LOCKED` i limitem dwóch aktywnych slotów odzyskuje wygasłe lease; worker komunikuje się tylko przez service-role RPC.
- FastAPI zapisuje job natychmiast przez `/api/jobs/research`, a worker uruchamia istniejący CLI poza requestem. Statusy, zdarzenia i usage są odczytywane z PostgreSQL; manifesty legacy pozostały wyłącznie artefaktem diagnostycznym. Przekroczenie limitu stron/tokenów/kosztu albo timeout kończy job jako `partial`; anulowanie jest sprawdzane przed etapami i przed ich zakończeniem.
- UI kreatora oraz historii jobów korzysta z `/api/jobs` do enqueue, pollingu, listy i anulowania; lease `leased` pozostaje aktywny i możliwy do anulowania. Żaden sekret service-role nie trafia do frontendu.
- Testy Unit 5: focused backend 32 PASS, frontend 17 PASS, `pnpm run typecheck` PASS, `pnpm run build` PASS (istniejące nieblokujące ostrzeżenie Vite o chunku >500 kB), `bash scripts/check_fieldnote.sh` PASS oraz `git diff --check` PASS. Bramka offline obejmuje teraz testy kolejki.
- Pełny review Unit 5 (`e04145b^..e04145b`) objął correctness, security, tests, UI i data. Powtórzono focused backend (32 PASS), frontend (17 PASS), typecheck, pełny `bash scripts/check_fieldnote.sh` i `git diff --check` — wszystkie automatyczne komendy PASS.
- Gate Unit 5: **BLOKUJE** — 5 P1, 6 P2, 0 P3. P1: bezpośredni DML analysta omija control plane kolejki; heartbeat nigdy nie wykonuje pierwszego odnowienia; selekcja źródeł nie trafia do CLI; limity/usage/retry nie ograniczają płatnego wykonania; cancel/timeout nie chroni przed późniejszym commitem. P2 obejmują brak runtime testu PostgreSQL, recovery anulowanego lease, błędne ID eventów, fałszywy total, migający/racy polling i niepełny DTO.
- Raport: `docs/active/fieldnote-stroller-mvp/review-unit-5.md`. Kod nie został zmieniony podczas review; Unit 6 nie został rozpoczęty.

## Przekazanie

- **Bieżący unit:** Unit 5 — Kolejka PostgreSQL i worker z dwoma slotami.
- **Status:** implementacja Unit 5 zakończona; oczekuje ograniczonego re-review.
- **Ostatnie testy:** runtime Supabase 6 PASS, focused backend 32 PASS, offline gate uruchomiony, `git diff --check` PASS.
- **Bloker:** brak; wynik PASS Unit 5 wymaga jeszcze re-review testu runtime.
- **Następny krok:** `$dev-docs-review docs/active/fieldnote-stroller-mvp 5` — ograniczony re-review wyłącznie testu PostgreSQL concurrency/RLS; nie rozpoczynaj Unit 6.

### Unit 5 — naprawa trzech P2 runtime queue contract

- Naprawiono wyłącznie trzy zaakceptowane P2 w `tests/test_supabase_runtime_contract.py`:
  wyścig o `p_max_active=1` asercją obejmuje wszystkie odpowiedzi, stale lease
  jest odrzucany również przez `fieldnote_start_research_job`, a aktualny token
  przechodzi do `running`; po recovery anulowanego joba test tworzy nowy job dla
  tego samego produktu i potwierdza zwolnienie aktywnej blokady.
- Weryfikacja po poprawce obejmuje focused runtime, pełny runtime contract,
  focused backend, `git diff --check` oraz pełny offline gate. Unit 6 nie rozpoczęto.
- Status: implementacja poprawki zakończona; oczekuje ograniczony re-review
  wyłącznie tych trzech P2.

### Unit 5 — wykonanie napraw review

- Naprawiono zaakceptowane P1/P2: service-role-only DML kolejki, heartbeat/fencing, immutable context selekcji, limity i retry, process-group cancel/timeout, recovery anulowanych lease, mapowanie eventów, total/paginację oraz odporne UI i DTO.
- Weryfikacja: backend 32 PASS, frontend 20 PASS, typecheck/build PASS, `bash scripts/check_fieldnote.sh` PASS, `git diff --check` PASS.
- Status: poprawki P1/P2 zakończone; Unit 5 oczekuje ograniczonego re-review. Unit 6 nie rozpoczęto.

### Unit 5 — ograniczony re-review trzech P2 runtime queue contract

- Zakres: `19019ff..8fa7fd4`, wyłącznie rozszerzenie lokalnego testu
  PostgreSQL/PostgREST oraz dokumentacja Unit 5. Correctness i security review
  wykonały niezależne subagenty; test/data wykonano jako single-agent fallback,
  bo limit wątków nie pozwolił uruchomić kolejnych agentów.
- Zamknięte: asercja wszystkich odpowiedzi wyścigu, stale/current fencing
  `fieldnote_start_research_job` oraz udany nowy job po terminalizacji
  anulowanego lease.
- Przyjęto 1 P2: runtime contract nie próbuje utworzyć duplikatu dla produktu,
  gdy pierwszy job jest aktywny, więc nie dowodzi wykonawczo odmowy unique
  active-product indexu przed recovery.
- Weryfikacja: runtime Supabase 6 PASS, focused backend 32 PASS, pełna
  `bash scripts/check_fieldnote.sh` PASS, `git diff --check 19019ff..8fa7fd4`
  PASS. Gate Unit 5: **WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3; Unit 6 nie rozpoczęto.

### Unit 5 — naprawa P2 aktywnego duplikatu produktu

- Zmieniono wyłącznie `tests/test_supabase_runtime_contract.py`: po leasowaniu
  joba test wykonawczo próbuje utworzyć drugi job tego samego produktu i wymaga
  błędu indeksu `research_jobs_one_active_per_product`. Istniejący udany insert
  po cancel recovery pozostaje pozytywną asercją zwolnienia blokady.
- Weryfikacja: focused opt-in runtime test PASS, pełny runtime Supabase 6 PASS,
  focused backend 32 PASS, pełny `bash scripts/check_fieldnote.sh` PASS oraz
  `git diff --check` PASS. Nie użyto płatnych API ani nie rozpoczęto Unit 6.
- Status: implementacja P2 zakończona; Unit 5 oczekuje ograniczonego re-review
  wyłącznie tej regresji.

### Unit 5 — końcowy ograniczony re-review P2

- Zakres: `8fa7fd4..b59d169`, wyłącznie wykonawcza asercja odmowy drugiego
  aktywnego joba tego samego produktu oraz jej regresja. Correctness i security
  sprawdziły subagenty; test/data wykonano jako single-agent fallback z powodu
  limitu wątków. Nie uruchamiano UI review, bo diff nie dotyczył frontendu.
- Wynik: PASS. Runtime test wymaga błędu nazwanego indeksu
  `research_jobs_one_active_per_product`, a po cancel recovery potwierdza
  ponowne utworzenie joba. Nie znaleziono P1, P2 ani P3.
- Weryfikacja: runtime Supabase 6 PASS, focused backend 32 PASS, pełna
  `bash scripts/check_fieldnote.sh` PASS, `python3 -m py_compile` PASS oraz
  `git diff --check b59d169^..b59d169` PASS. Unit 6 nie rozpoczęto.

### Unit 5 — ograniczony re-review runtime PostgreSQL/RLS

- Zakres: wyłącznie otwarty P2 wymagający wykonawczego lokalnego testu kolejki,
  `e04145b..8c50b59`.
- Reviewers: correctness, security, tests i data. Wszystkie cztery perspektywy
  potwierdziły ten sam brak; nie znaleziono dodatkowych findings w zakresie.
- Weryfikacja: focused queue/worker/runtime suite PASS (13 testów, 5 opt-in
  skipped), `git diff --check 8c50b59^..8c50b59` PASS. Lokalny `supabase status`
  nie uruchomił się w sandboxie, ponieważ CLI próbował zapisać telemetry poza
  workspace; nie zmienia to findingu, bo nie istnieje test queue RPC do uruchomienia.
- Gate Unit 5: **WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3. P2: dodać opt-in lokalny
  test realnego PostgreSQL/PostgREST dla limitu dwóch slotów, współbieżnego
  claimu, recovery/fencing i odmowy queue DML anon/analyst.
- Unit 6 nie rozpoczęto.

### Unit 5 — domknięcie P2 runtime testem

- Dodano `test_durable_queue_rpc_concurrency_fencing_and_rls` do opt-in suite.
  Test korzysta z aktualnego lokalnego Supabase, równoległych żądań PostgREST
  do RPC claim, service-role RPC start/heartbeat/complete/cancel oraz JWT anon i
  analyst dla odmowy INSERT/PATCH/DELETE na jobs/events. Nie zapisuje sekretów.
- Zakres testu obejmuje dokładnie dwa z trzech aktywnych claimów, jednego
  zwycięzcę wyścigu o job, recovery wygasłego lease, stale-token fencing oraz
  terminalizację wygasłego anulowanego joba.
- Weryfikacja: `FIELDNOTE_SUPABASE_INTEGRATION=1 ... test_supabase_runtime_contract.py`
  — 6 PASS; focused backend — 32 PASS; `git diff --check` — PASS; offline gate
  uruchomiony, frontendowy check pozostaje bez zmian.
- Status: implementacja Unit 5 zakończona, oczekuje re-review. Unit 6 nie rozpoczęto.

### Unit 5 — ograniczony re-review runtime queue contract

- Zakres: wyłącznie `8c50b59..19019ff` i wykonawczy test PostgreSQL/RLS.
  Correctness i test reviewer wykryli trzy P2; security reviewer PASS. Data
  reviewer został uruchomiony dla zmian kolejki, ale nie zwrócił wyniku przed
  zakończeniem fali; findingi zweryfikowano bezpośrednio w teście.
- P2: test wyścigu filtruje tylko jeden job zamiast wszystkich odpowiedzi;
  stale fencing nie sprawdza RPC start; cancel recovery nie dowodzi zwolnienia
  unique active-product indexu.
- Weryfikacja: focused backend 32 PASS, opt-in runtime test PASS jako napisany,
  `git diff --check 8c50b59..19019ff` PASS.
- Gate Unit 5: **WYMAGA POPRAWEK** — 0 P1, 3 P2, 0 P3. Unit 6 nie rozpoczęto.

### Unit 5 — końcowy status po re-review

- Zakres końcowego commitu `8fa7fd4..b59d169` został sprawdzony; Unit 5 ma
  **PASS** i brak otwartych P1/P2. Dokumentem źródłowym wyniku jest
  `review-unit-5.md`; wcześniejsze historyczne findingi pozostają tam jako
  ślad procesu, ale nie są aktywnymi blokadami.

### Unit 6 — przyrostowe commitowanie i przeliczanie

- Dodano neutralny względem repozytorium `BenchmarkRebuildService` z jawnymi
  `product_scope` i `benchmark_group_scope`, kanonicznym hashem semantycznym,
  progiem zmiany ceny 5% oraz snapshotem tworzonym wyłącznie po istotnej
  zmianie domeny.
- `scripts/rebuild_product_scope.py` wykonuje tylko rebuild wskazanego produktu
  i blokadę produktu; odrzuca pracę, gdy aktywna jest blokada administracyjnego
  full rebuildu. `scripts/rebuild_all_admin.py` jest oddzielnym poleceniem
  administracyjnym i serializuje pełny rebuild przez `aggregation.lock`.
- Etapy benchmarku i coverage w kanonicznym runnerze przyjmują `--group-key`
  w scoped runie i nie używają globalnej blokady ani frontendowego eksportu;
  globalne zachowanie bez scope pozostaje kompatybilne dla maintenance.
- Weryfikacja: `tests/test_incremental_pipeline.py` i
  `tests/test_incremental_benchmark_rebuild.py` — 7 PASS; testy backendowe
  Unit 5 — 32 PASS; `py_compile` nowych/zmienionych modułów, pełna
  `bash scripts/check_fieldnote.sh` oraz `git diff --check` — PASS.
- Status: implementacja Unit 6 zakończona; oczekuje niezależnego review.
  Unit 7 nie rozpoczęto.

### Unit 6 — pełny review

- Zakres: `b59d169..1e37e3e`. Correctness, security i test reviewer pracowali
  niezależnie; data review wykonano jako single-agent fallback po braku wyniku
  warunkowego subagenta. UI review nie był wymagany.
- Weryfikacja review: focused Unit 6 7 PASS, `git diff --check
  b59d169..1e37e3e` PASS oraz pełna `bash scripts/check_fieldnote.sh` PASS.
- Gate: **BLOKUJE** — 3 P1, 2 P2, 0 P3. P1: no-context canonical CLI nadal
  przebudowuje globalnie; scoped read–merge–commit i admin rebuild mogą się
  ścigać; semantic snapshoty są tylko fixtureem i nie są utrwalane przez
  worker/Supabase. P2: stale rows po utracie eligibility oraz niedostateczne
  testy izolacji grup/canonical pipeline.
- Nie zmieniano kodu podczas review. Unit 6 pozostaje otwarty; Unit 7 nie
  rozpoczęto. Pełny raport: `review-unit-6.md`.

### Unit 6 — remediacja findings P1/P2

- Kanoniczny runner wylicza teraz `product_scope` również bez przekazanego
  contextu i zawsze uruchamia benchmark/coverage z `--group-key`; etapy 8–9
  nie wywołują globalnego eksportu. Commit scope zawiera ograniczoną projekcję
  group/model-state/benchmark/coverage oraz medianę ceny wyłącznie z
  zresearchowanych źródeł.
- JSON fixture CLIs wykonują wspólną, retryowaną transakcję locka obejmującą
  read–merge–write; drugi scope odczytuje już zapisany canonical output, a
  jawny admin full rebuild korzysta z tego samego protokołu. Produkcyjny
  boundary jest pojedynczym fenced RPC PostgreSQL z advisory transaction lock,
  które atomowo tworzy snapshoty i terminalizuje job.
- Dodano `research_scope_snapshots`, `BenchmarkCommitService` i
  `JobRepository.complete_incremental()`. Worker nie raportuje `succeeded`/
  `partial`, gdy scoped envelope lub trwały commit nie przejdzie; status
  końcowy jest wtedy `failed`.
- Builder benchmarku i coverage usuwają stare wiersze żądanej grupy przed
  merge, także po utracie eligibility. Regresje obejmują dwie grupy,
  canonical commands, 4,99%/5%, trwały envelope, brak lost update dla dwóch
  równoległych scope'ów oraz adminowy rebuild.
- Weryfikacja remediacji: focused Unit 6 + lease/schema/RLS contracts — 27
  PASS; `py_compile` zmienionych modułów PASS; `git diff --check` PASS; pełna
  `bash scripts/check_fieldnote.sh` PASS. `supabase migration up --local`
  zastosowało migrację, a bezpieczne query schematu potwierdziło tabelę
  `research_scope_snapshots` i RPC `fieldnote_commit_incremental_research_job`.
  Unit 6 oczekuje ograniczonego re-review, Unit 7 nie rozpoczęto.

### Unit 6 — ograniczony re-review commitu `002c371`

- Zakres: wyłącznie `002c371^..002c371` i pięć findings poprzedniego review.
  Correctness, security, tests i data pracowali niezależnie; UI review nie był
  wymagany. Nie zmieniano kodu i nie rozpoczęto Unit 7.
- Weryfikacja: focused Unit 6 + queue/schema/RLS — 27 PASS; pełna
  `bash scripts/check_fieldnote.sh` PASS; `git diff --check 002c371^ 002c371`
  PASS. Wykonawca potwierdził lokalne zastosowanie migracji i obecność tabeli
  oraz RPC bez ujawniania kluczy.
- Gate: **BLOKUJE** — 2 P1, 4 P2, 0 P3. P1: `scoped_commit_payload()` usuwa
  pola ceny zanim liczy medianę, więc 5% price snapshot nie może powstać;
  worker mapuje no-mutation `partial` (page-limit/timeout) na `failed`, gdy
  committer nie dostaje envelope. P2: brakuje testów realnego direct CLI,
  overlap admin/scoped, runtime PostgreSQL fenced RPC oraz builderów po
  utracie eligibility.
- Następny krok: naprawa wyłącznie tych 2 P1 i 4 P2 w Unit 6, potem kolejny
  ograniczony re-review. Pełny raport: `review-unit-6.md`.

### Unit 6 — wykonanie remediacji po review `002c371`

- Naprawiono wyłącznie zaakceptowane 2 P1 i 4 P2. `scoped_commit_payload()`
  liczy medianę z pełnych source records przed projekcją identifier-only.
  No-mutation `partial` z preflight page-limit lub timeoutu przechodzi przez
  fenced incremental RPC z pustą listą snapshotów i zachowuje status `partial`.
- Dodano wykonawczy direct-CLI test bez contextu, overlap test dwóch scope'ów
  z admin full rebuildem, builder integration test usuwający stale
  benchmark/source rows oraz lokalny runtime contract RPC dla 4,99%/5%, stale
  lease i invalid envelope. Poprawiono alias zmiennej `value` w SQL RPC.
- Weryfikacja: focused Unit 6/schema/RLS — 28 PASS; opt-in test nowego RPC —
  PASS; `py_compile` — PASS; pełny `bash scripts/check_fieldnote.sh` — PASS;
  `git diff --check` — PASS. Nie rozpoczęto Unit 7.
- Status: implementacja zakończona; dokumentacja oczekuje ograniczonego
  re-review wyłącznie `002c371^..HEAD`.

### Unit 6 — ograniczony re-review commitu `c35f1d7`

- Zakres: wyłącznie `002c371..c35f1d7` oraz regresje sześciu wcześniejszych
  findings P1/P2. Pracowali niezależnie correctness, security, tests i data;
  UI review nie był wymagany. Nie zmieniano kodu ani nie rozpoczęto Unit 7.
- Weryfikacja review: focused Unit 6/schema/RLS — 28 PASS; opt-in lokalny
  runtime RPC — 1 PASS; `py_compile`, `git diff --check c35f1d7^ c35f1d7` i
  pełna `bash scripts/check_fieldnote.sh` — PASS.
- Gate: **BLOKUJE** — 2 P1, 1 P2, 0 P3. P1: group snapshot dziedziczy
  `price_median` z payloadu produktu, więc zmiana 4,99% tworzy snapshot;
  poprawiony RPC zmienia już zarejestrowaną migrację `202607290001`, więc nie
  przejdzie na bazę po wcześniejszym deployu. P2: test scoped/admin nie
  wymusza deterministycznego nakładania krytycznych sekcji. Security review:
  PASS. Szczegóły w `review-unit-6.md`.
- Następny krok: naprawić wyłącznie te 2 P1 i 1 P2 w Unit 6, dodać migrację
  następczą oraz wykonać ograniczony re-review. Unit 7 pozostaje poza zakresem.

### Unit 6 — wykonanie remediacji po review `c35f1d7`

- Naprawiono wyłącznie 2 P1 i 1 P2: `_snapshots()` emituje snapshot grupy
  tylko z jawnego `internal_benchmark`/`internal_benchmarks`, historyczna
  migracja `202607290001` jest niezmieniona, a `202607300001` dostarcza
  poprawiony fenced RPC. Fixture concurrency ma deterministyczny hook po
  zdobyciu locka i potwierdza, że admin czeka na scoped commit.
- Zmienione pliki implementacyjne/testowe: `fieldnote-api/services/benchmark_commit_service.py`,
  `fieldnote-api/services/benchmark_rebuild_service.py`,
  `supabase/migrations/202607290001_incremental_benchmark_commit.sql`,
  `supabase/migrations/202607300001_incremental_commit_partial_fixes.sql`,
  `tests/test_incremental_benchmark_rebuild.py` i
  `tests/test_supabase_schema_contract.py`.
- Weryfikacja: focused Unit 6/schema/RLS — 30 PASS; `py_compile` i
  `git diff --check` — PASS; `supabase db reset --local --yes` zastosował
  migracje `202607290001` i `202607300001`; lokalny runtime RPC — 1 PASS;
  pełna `bash scripts/check_fieldnote.sh` — PASS.
- Status: implementacja remediacji zakończona i gotowa do ograniczonego
  re-review commitu wykonawczego; Unit 6 nie jest jeszcze oznaczony jako
  ukończony, Unit 7 nie rozpoczęto.

### Unit 6 — wykonanie P2 po re-review `395abc9`

- Naprawiono wyłącznie zaakceptowany P2: dodano opt-in test upgrade'u lokalnej
  bazy, w którym `202607290001` pozostaje zastosowana, usuwany jest wyłącznie
  wpis `202607300001`, a `supabase migration up --local --yes` stosuje następcę
  bez resetu. Test następnie wykonuje oba poprawione RPC: no-mutation `partial`
  bez snapshotu oraz `succeeded` z JSON snapshotem.
- Test używa jednego polecenia SQL instalującego baseline sentinel, ponieważ
  `supabase db query` nie przyjmuje wielu komend w prepared statement; po
  migracji następczej sentinel jest zastępowany produkcyjnym RPC. Fixture'y są
  unikalne i sprzątane w `finally`.
- Weryfikacja: focused Unit 6/schema/RLS — 30 PASS; opt-in runtime RPC i test
  upgrade'u — 2 PASS; `py_compile` — PASS; `git diff --check` — PASS; pełna
  `bash scripts/check_fieldnote.sh` — PASS. Nie rozpoczęto Unit 7.
- Status: implementacja P2 zakończona; Unit 6 oczekuje ograniczonego
  re-review wyłącznie tej poprawki.

### Unit 6 — ograniczony re-review commitu `395abc9`

- Zakres: wyłącznie `c35f1d7..395abc9` i trzy naprawy poprzedniego review.
  Correctness, security, tests i data pracowali niezależnie; UI review nie był
  wymagany. Nie zmieniano kodu ani nie rozpoczęto Unit 7.
- Correctness, security i data: PASS. Potwierdzono brak price leakage do
  snapshotu grupy, niezmienność historycznej migracji oraz bezpieczne
  zastąpienie RPC przez `202607300001`. Data review potwierdził, że bieżący
  pipeline nie emituje agregatu grupowego, więc pominięcie takiego snapshotu
  jest właściwe.
- Gate: **WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3. Test reviewer przyjął P2:
  obecne testy analizują tekst migracji i resetują świeżą bazę, ale nie
  wykonują upgrade'u istniejącej historii `202607290001` przez samą migrację
  `202607300001`.
- Weryfikacja review: focused Unit 6/schema/RLS — 30 PASS; opt-in lokalny RPC
  — 1 PASS; pełna `bash scripts/check_fieldnote.sh` i `git diff --check
  c35f1d7..395abc9` — PASS.
- Następny krok: naprawić wyłącznie wykonawczy test upgrade'u migracji i
  wykonać kolejny ograniczony re-review Unit 6. Unit 7 pozostaje poza zakresem.

### Unit 6 — ograniczony re-review commitu `c3646b7`

- Zakres: wyłącznie `395abc9..c3646b7`, czyli testowy P2 upgrade'u migracji
  oraz jego dokumentacja. Correctness, security, tests i data pracowali
  niezależnie; UI review nie był wymagany. Nie zmieniano kodu ani nie
  rozpoczęto Unit 7.
- Wszyscy reviewerzy: PASS. Test pozostawia `202607290001` w historii,
  odtwarza pending `202607300001` bez resetu, wykonuje jego zastosowanie i
  przez PostgREST potwierdza no-mutation `partial` oraz JSON snapshot.
- Weryfikacja review: focused Unit 6/schema/RLS — 30 PASS; opt-in lokalne RPC
  i upgrade — 2 PASS; `git diff --check 395abc9..c3646b7` — PASS; pełna
  `bash scripts/check_fieldnote.sh` — PASS.
- Gate: **GOTOWE DO KONTYNUACJI** — 0 P1, 0 P2, 0 P3. Unit 6 jest ukończony;
  Unit 7 nie został rozpoczęty.

### Unit 7 — implementacja wspólnego Firecrawl i katalogu konkurencji

- Zakres wykonania obejmuje wyłącznie Unit 7. Dodano `scripts/firecrawl_client.py`
  z v2 Search/Scrape/Crawl, retry dla 429/5xx, limitami stron, usage i cache;
  adaptery Allegro/Amazon/retailer/manufacturer korzystają z tego samego
  `NormalizedSourceContent` i kontraktu provenance. Zmieniono fetchery ofert i
  producenta tak, aby live pobrania przechodziły przez wspólnego klienta;
  bezpośredni HTTP w skrypcie producenta jest tylko jawnie włączonym trybem
  developerskim.
- Dodano `scripts/discover_manufacturer_catalog.py`,
  `scripts/normalize_product_aliases.py`, `config/sources/strollers.yaml`,
  preview API `fieldnote-api/services/brand_catalog_service.py` + router oraz
  offline fixtures w `fixtures/firecrawl/`. Discovery wyklucza akcesoria/
  placeholdery, zachowuje jawny `review_required` dla realnych rekordów bez
  grupy, a aliasy ignorują kolor i nie scalają konfiguracji 2w1/3w1.
- Testy Unit 7: `python3 -m unittest tests/test_firecrawl_client.py
  tests/test_firecrawl_source_adapters.py tests/test_manufacturer_catalog_discovery.py
  tests/test_product_aliases.py` — 11 PASS. Weryfikacja istniejących kontraktów
  producenta na `fieldnote-api/.venv/bin/python` — 18 PASS; `py_compile` — PASS;
  pełna `bash scripts/check_fieldnote.sh` — PASS; `git diff --check` — PASS.
- Status: implementacja i dokumentacja Unit 7 zakończone; niezależny review
  Unit 7 pozostaje wymagany. Unit 8 nie rozpoczęto.

### Unit 7 — pełny review

- Zakres review: `696c19e..192a8a5`; użyto niezależnie
  correctness_reviewer, security_reviewer, test_reviewer i data_reviewer. Nie
  zmieniano kodu ani nie rozpoczęto Unit 8.
- Weryfikacja: focused Unit 7 — 11 PASS; API/auth regression — 27 PASS;
  `git diff --check 696c19e..192a8a5` — PASS; pełna
  `bash scripts/check_fieldnote.sh` — PASS. Testy nie wywoływały Firecrawl ani
  OpenAI.
- Gate: **BLOKUJE** — 5 P1, 2 P2, 0 P3. Zaakceptowano: obsługę timeout/429 i
  stale queue errors, fałszywy PASS dla niezaklasyfikowanego katalogu,
  nieczynny refresh producenta, błędną tożsamość aliasów, uszkodzony PDF
  manuala, akceptację innego modelu oraz nieograniczony `fixture_root` API.
- Następny krok: naprawić wyłącznie zaakceptowane P1/P2 Unit 7 zgodnie z
  `review-unit-7.md`, a potem wykonać ograniczony re-review. Unit 8 pozostaje
  poza zakresem.

### Unit 7 — remediation zaakceptowanych 5 P1 i 2 P2

- Naprawiono retry/normalizację timeoutów transportu Firecrawl oraz obsługę
  `FirecrawlError` w kolejce ofert, aby błędy providerów były zapisywane jako
  `error` zamiast kończyć się tracebackiem. Quality gate discovery i bieżący
  katalog wyliczają niesklasyfikowane realne rekordy; adminowy preview waliduje
  markę, korzysta z `catalog_urls` i wspólnego klienta oraz ogranicza
  `fixture_root` do `fixtures/firecrawl/manufacturer` po `resolve()`.
- Fixture discovery dodatkowo przepuszcza wyłącznie allowlistę pól katalogu,
  więc nawet poprawnie położony JSON nie może wyprowadzić sekretów lub pól
  diagnostycznych przez preview API.
- Alias identity stripuje kolory i wyprowadza konfigurację z title-only recordów,
  dzięki czemu 2w1/3w1 nie są scalane. Adapter wymaga modelu w tytule i odrzuca
  wzmiankę kompatybilności. Fetcher producenta żąda artefaktu PDF i sprawdza
  magic bytes `%PDF` przed zapisem `document.pdf`.
- Dodano regresje timeout/retry, błędu kolejki 429, jakości katalogu, discovery
  z oficjalnego URL, bezpiecznego fixture root, aliasów, kompatybilności modelu
  oraz PDF. Focused remediation suite: 21 PASS; `py_compile`, `git diff --check`
  i pełna `bash scripts/check_fieldnote.sh` — PASS.
- Status: implementacja remediation zakończona; review-unit-7 pozostaje
  niezamknięty do ograniczonego re-review. Unit 8 nie rozpoczęto.

### Unit 7 — ograniczony re-review commitu `f7ed8e3`

- Zakres: wyłącznie `192a8a5..f7ed8e3`, czyli remediation poprzednich 5 P1 i
  2 P2 oraz ich regresje. Użyto correctness_reviewer, security_reviewer,
  test_reviewer i data_reviewer; UI review nie był wymagany. Nie zmieniano
  kodu ani nie rozpoczęto Unit 8.
- Security reviewer: PASS. Correctness potwierdził dwa P1: pusty poprawny
  response official discovery raportuje `success/pass`, a `--resume` uznaje
  istniejący HTML `document.pdf` za poprawnie pobrany. Test reviewer przyjął
  dwa P2 (brak regresji provider `partial` oraz symlink/API 422), a data
  reviewer przyjął P2: wynik deduplikacji statusu/grupy zależy od kolejności
  duplikatów producenta.
- Weryfikacja review: focused remediation suite — 21 PASS;
  `git diff --check 192a8a5..f7ed8e3` — PASS; pełna
  `bash scripts/check_fieldnote.sh` — PASS. Odtworzono puste live discovery,
  legacy HTML PDF przy `--resume` oraz order-dependent classification.
- Gate: **BLOKUJE** — 2 P1, 3 P2, 0 P3. Unit 7 nie jest ukończony; naprawić
  wyłącznie te pięć findings i następnie wykonać ograniczony re-review. Unit 8
  pozostaje poza zakresem.

### Unit 7 — wykonanie remediation 2 P1 i 3 P2

- Pusty lub nierozpoznany live payload official discovery zwraca teraz
  kontrolowany `partial` z `quality_gate=review`. Resume manuala PDF ponownie
  pobiera artefakt, jeśli istniejący `document.pdf` nie ma sygnatury `%PDF`.
- Dodano test provider `FirecrawlError` → `partial`, regresję pustego payloadu,
  symlink escape i route 422, a także test order-independent deduplikacji oraz
  konfliktu grup benchmarkowych. Deduplikacja wybiera metadane deterministycznie
  i oznacza sprzeczne grupy jako `review_required`.
- Weryfikacja: focused Unit 7 — 26 PASS; API venv test — 10 PASS;
  `py_compile` i `git diff --check` — PASS; pełna
  `bash scripts/check_fieldnote.sh` — PASS. Nie wywołano płatnych API.
- Status: implementacja remediation zakończona; dokumentacja oczekuje
  ograniczonego re-review Unit 7. Unit 8 nie rozpoczęto.

### Unit 7 — finalny ograniczony re-review commitu `3e45506`

- Zakres: wyłącznie `f7ed8e3..3e45506` i pięć ostatnich poprawek. Użyto
  correctness_reviewer, security_reviewer, test_reviewer oraz data_reviewer;
  UI review nie był wymagany. Nie zmieniano kodu ani nie rozpoczęto Unit 8.
- Security i tests: PASS. Correctness potwierdził P1: pairwise merge trzech
  kart może utracić wcześniejszy konflikt grup i zwrócić `pass`, zależnie od
  kolejności. Data review potwierdził P2: merge zachowuje tylko jeden singular
  `source_id` i nie buduje pełnego `source_ids` provenance.
- Weryfikacja: focused Unit 7 — 26 PASS; API venv — 10 PASS;
  `git diff --check f7ed8e3..3e45506` — PASS; pełna
  `bash scripts/check_fieldnote.sh` — PASS. Odtworzono wszystkie permutacje
  trzech kart A/B/A oraz utratę drugiego source ID.
- Gate: **BLOKUJE** — 1 P1, 1 P2, 0 P3. Unit 7 nie jest ukończony; naprawić
  wyłącznie te dwa findings i ponowić ograniczony re-review. Unit 8 pozostaje
  poza zakresem.

### Unit 7 — wykonanie remediation P1/P2 po re-review `3e45506`

- Naprawiono wyłącznie oba zaakceptowane findings w `scripts/normalize_product_aliases.py`:
  wszystkie rekordy tej samej tożsamości są agregowane jednocześnie, więc
  konflikt `benchmark_group` pozostaje nieodwracalny i daje `review_required`;
  `source_ids` jest deterministyczną unią singularnych `source_id` oraz
  istniejących list provenance, z pierwszym ID jako stabilnym primary.
- Dodano regresje wszystkich permutacji kart A/B/A oraz pełnej unii source IDs
  w `tests/test_product_aliases.py`. Nie zmieniono adapterów, API ani danych
  produkcyjnych i nie rozpoczęto Unit 8.
- Weryfikacja: focused Unit 7 — 28 PASS; `fieldnote-api/.venv/bin/python -m
  unittest tests/test_unit7_review_remediation.py` — 10 PASS; `py_compile`,
  `git diff --check` oraz pełna `bash scripts/check_fieldnote.sh` — PASS.
- Status: implementacja remediation zakończona i zacommitowana; Unit 7 nadal
  oczekuje ograniczonego `$dev-docs-review` wyłącznie dla tego P1/P2.

### Unit 7 — ograniczony re-review commitu `347a9d9`

- Zakres: wyłącznie `3e45506..347a9d9`, czyli agregacja wszystkich duplikatów
  aliasu oraz deterministyczna unia `source_ids`. Użyto niezależnie
  `correctness_reviewer`, `security_reviewer`, `test_reviewer` i
  `data_reviewer`; UI review nie był wymagany. Nie zmieniano kodu ani nie
  rozpoczęto Unit 8.
- Security i tests: PASS. Correctness i data niezależnie potwierdziły jeden
  P1: logika grup używa `benchmark_group or benchmark_group_key`, więc
  sprzeczne, równocześnie ustawione pola jednej karty mogą zostać zredukowane
  do pojedynczej wartości i fałszywie zwrócić `classified/pass`.
- Weryfikacja re-review: focused `tests/test_product_aliases.py` — 7 PASS;
  `py_compile scripts/normalize_product_aliases.py` — PASS. Bezpośrednia
  reprodukcja konfliktu pól wykazała fałszywe `classified/light_stroller`.
  Nie uruchamiano ponownie pełnej offline bramki, ponieważ lokalne,
  niezwiązane zmiany Auth/Supabase brudzą worktree, a wcześniejsza próba
  zatrzymała się w teście hygiene. Executor uprzednio raportował focused 28
  PASS, remediation 10 PASS, `git diff --check` i pełny offline gate PASS.
- Gate: **BLOKUJE** — 1 P1, 0 P2, 0 P3. Naprawić wyłącznie agregację obu pól
  grupy oraz dodać regresję permutacji; potem ponowić ograniczony re-review.
  Unit 8 pozostaje poza zakresem.

### Unit 7 — wykonanie remediation P1 po re-review `347a9d9`

- W `scripts/normalize_product_aliases.py` agregacja grup zbiera teraz każdą
  niepustą wartość z obu pól `benchmark_group` i `benchmark_group_key` dla
  wszystkich kandydatów. Dowolna rozbieżność pozostaje nieodwracalnym
  `review_required/conflicting_benchmark_groups`.
- Dodano regresję permutacyjną w `tests/test_product_aliases.py` oraz test
  wykonawczy discovery w `tests/test_unit7_review_remediation.py`; oba warianty
  kolejności zwracają `quality_gate=review` i dokładnie jeden rekord do review.
- Weryfikacja: `tests/test_product_aliases.py`,
  `tests/test_unit7_review_remediation.py` i
  `tests/test_manufacturer_catalog_discovery.py` — 23 PASS; `py_compile` oraz
  `git diff --check` — PASS. Pełna `bash scripts/check_fieldnote.sh` ponownie
  zatrzymała się w istniejącym teście hygiene podczas `git show` na bieżącym
  brudnym drzewie i została przerwana; nie jest to regresja tej poprawki.
- Status: poprawka wykonana, dokumentacja zaktualizowana, Unit 7 oczekuje
  ograniczonego re-review wyłącznie tego P1. Unit 8 nie rozpoczęto.

### Unit 7 — końcowy ograniczony re-review `360972e^..360972e`

- Zakres obejmował wyłącznie naprawę konfliktu `benchmark_group` /
  `benchmark_group_key` i jej testy regresyjne. Użyto
  correctness_reviewer, security_reviewer, test_reviewer oraz data_reviewer;
  UI review nie był wymagany. Nie zmieniano kodu podczas review i nie
  rozpoczęto Unit 8.
- Wszyscy reviewerzy: PASS. Agregacja zbiera obie wartości z każdej karty,
  konflikt wewnątrz rekordu lub między aliasami daje `review_required`, a
  discovery zwraca `quality_gate=review`; aliasy, konfiguracja i `source_ids`
  pozostają zachowane.
- Weryfikacja: `git diff --check 360972e^..360972e`, `py_compile` i focused
  Unit 7 — 23 PASS. Pełna offline bramka nie została oznaczona jako powtórzona:
  zatrzymuje się w istniejącym teście hygiene na `git show` przy niezwiązanych
  lokalnych zmianach Auth/Supabase.
- Gate: **GOTOWE DO KONTYNUACJI** — 0 P1, 0 P2, 0 P3. Unit 7 ukończony;
  Unit 8 nie został rozpoczęty.

### Unit 8 — implementacja audytu atrybutów i względnego scoringu

- Dodano wersjonowany schema `config/categories/strollers.v1.yaml` z dokładnie
  21 polami, typami, jednostkami, rolami i wagami profili `urban`, `terrain`,
  `travel`. Plik używa składni JSON poprawnej jako YAML, aby testy offline nie
  wymagały dodatkowego parsera.
- `scripts/audit_stroller_attributes.py` audytuje 34 pliki
  `data/internal_specs/lionelo__*.json` i generuje
  `docs/audit/STROLLER_ATTRIBUTE_AUDIT.md`. Scoring normalizuje g→kg, mm→cm,
  boolowskie wartości i brak danych; brak pola obniża completeness, ale nie
  jest sztucznym zerem.
- Dodano `InternalBenchmarkService` (minimum 3 Lionelo w grupie),
  `CompetitiveBenchmarkService` (ta sama grupa i konfiguracja, maksymalnie 6)
  oraz `PricingService` (mediana/min/max i deduplikacja sprzedawcy). Cena jest
  osobnym agregatem i nie wpływa na utility score. Kontrakty otrzymały DTO
  score/price, a storage stabilny envelope snapshotu.
- Weryfikacja: 15 testów Unit 8 PASS, `py_compile` zmienionych modułów oraz
  `git diff --check` PASS. Nie wywołano AI ani płatnych API; istniejące
  endpointy legacy pozostały bez zmiany zachowania.
- Status: implementacja zakończona, Unit 8 oczekuje niezależnego
  `$dev-docs-review`. Unit 9 nie rozpoczęto.

### Planowanie Unit 8.5 — trwałe odświeżenie produktu (`2026-08-06`)

- Uzgodniony kierunek: ręczne odświeżenie pojedynczego produktu ma zawsze
  uruchamiać nowy Firecrawl Search Allegro i fresh Scrape, a następnie
  deterministyczną ekstrakcję oraz ograniczone OpenAI dla brakujących lub
  niejednoznacznych pól. Każdy run i jego źródła mają pozostać w historii.
- Audyt istniejącego flow wykazał, że obecne `--resume` może użyć starego
  listingu/snapshotu i pominąć AI dla zmienionej treści tego samego źródła.
  Dlatego nie rozszerzamy kosmetycznie starego refreshu, tylko planujemy
  trwały kontrakt `product_refresh` oparty o job, `content_hash`, PostgreSQL
  i prywatny Supabase Storage.
- Bezpieczna semantyka: historia i raw evidence są zapisywane zawsze; bieżące
  dane produktu są publikowane dopiero po quality gate. Konflikt, błąd,
  cancel lub partial zachowuje last-known-good. Identyczny refresh tworzy nowy
  wpis historii, lecz nie duplikuje source ani semantic snapshotu.
- Unit 8.5 został umieszczony po Unit 8 i przed Unit 9. UI przycisku oraz
  widoku historii pozostaje w Unit 9; Unit 8.5 dostarcza trwałe API/job/worker
  i kontrakt danych. Wykonanie nie może ruszyć przed końcowym PASS Unit 8.
- W tej sesji nie zmieniano kodu, nie uruchamiano Firecrawl/OpenAI ani innych
  płatnych providerów. Zmieniono wyłącznie dokumentację planu i aktywnego
  zadania.

### Unit 8 — pełny review `b71a991^..b71a991` (`2026-08-06`)

- Zakres: schema 21 atrybutów, offline audit, scoring, serwisy benchmarków i
  cen, kontrakty/snapshot envelope oraz testy Unit 8. Użyto niezależnie
  `correctness_reviewer`, `security_reviewer`, `test_reviewer` i
  `data_reviewer`; UI review nie był wymagany. Nie zmieniano kodu ani nie
  rozpoczęto Unit 8.5.
- Security: PASS. Correctness i data potwierdziły dwa P1: scoring/ceny nie są
  podłączone do runtime ani trwałych snapshotów oraz brak atrybutu zaniża
  utility score jak zero. Przyjęto także cztery P2: brak spójnego gate'u
  konfiguracji, niesprawne scored `suspension`, brak aliasów PL/EN/konwersji
  w schema i niewystarczające regresje core scoringu/cen/audytu.
- Weryfikacja: focused Unit 8 — 15 PASS; `git diff --check b71a991^..b71a991`
  — PASS. Pełny `bash scripts/check_fieldnote.sh` nie został ukończony:
  hygiene zatrzymał się w `git show :<tracked-path>` podczas skanowania
  śledzonych plików, więc nie oznaczono go jako PASS.
- Gate: **BLOKUJE** — 2 P1, 4 P2, 0 P3. Unit 8 pozostaje nieukończony;
  naprawić wyłącznie findings z `review-unit-8.md`, a potem wykonać ograniczony
  re-review. Unit 8.5 i Unit 9 pozostają poza zakresem.

### Unit 8 — wykonanie remediation P1/P2 (`2026-08-06`)

- Naprawiono wyłącznie findings z `review-unit-8.md`: runtime benchmark
  endpointy i pipeline scoped commit otrzymały projection scoringu/ceny;
  utility score używa per-product denominator; internal/competitive/manifests
  respektują konfigurację; `suspension` ma deterministyczną normalizację;
  schema ma aliasy PL/EN, collision checks i wersjonowane konwersje.
- Dodano regresje rankingu, missing-data, konfiguracji, suspension, aliasów,
  mediany/najnowszej ceny oraz dokładnego corpus 34 specyfikacji. Zmienione
  pliki kodu obejmują `app.py`, kontrakty/storage, usługi benchmarków,
  `benchmark_relative_scoring.py`, pipeline oraz testy Unit 8.
- Weryfikacja: focused Unit 8 — **20 PASS**; py_compile touched modules —
  PASS; `git diff --check` — PASS. FastAPI-dependent tests nie mogły zostać
  ukończone w globalnym interpreterze bez `fastapi`; uruchomienie z lokalnym
  venv zatrzymało się na odczycie dużego lokalnego corpus. Pełna bramka
  zatrzymała się w istniejącym hygiene `git show :<tracked-path>`; nie
  oznaczono jej jako PASS.
- Status: remediation zakończone, ale Unit 8 ma stan **partial** i oczekuje
  ograniczonego re-review. Zapisano jeden logiczny commit `feat: complete unit
  8 scoring integration`. Nie rozpoczęto Unit 8.5 ani Unit 9.

### Unit 8 — ograniczony re-review `0b985d0^..0b985d0` (`2026-08-06`)

- Zakres obejmował wyłącznie remediation poprzednich findings. Użyto
  `correctness_reviewer`, `security_reviewer`, `test_reviewer` i
  `data_reviewer`; UI review nie był wymagany. Nie zmieniano kodu ani nie
  rozpoczęto Unit 8.5.
- Security: PASS. Correctness, tests i data potwierdziły dwa P1: scoped
  semantic snapshot nie filtruje konfiguracji oraz competitive detail liczy
  inny skład niż manifest. Przyjęto P2 dla fałszywego `no_data` ceny internal
  i braku wykonawczych regresji API/commit/config-manifest.
- Weryfikacja: focused Unit 8 — 20 PASS; py_compile i
  `git diff --check 0b985d0^..0b985d0` — PASS. Pełna offline bramka nie została
  oznaczona jako PASS, ponieważ istniejący hygiene zatrzymuje się na
  `git show :<tracked-path>` w tym środowisku.
- Gate: **BLOKUJE** — 2 P1, 2 P2, 0 P3. Naprawić wyłącznie findings z
  `review-unit-8.md`, a potem wykonać kolejny ograniczony re-review. Unit 8.5
  i Unit 9 pozostają poza zakresem.

### Unit 8 — remediation po ograniczonym re-review (`2026-08-06`)

- Naprawiono wyłącznie cztery zaakceptowane findings: scoped pipeline filtruje
  konfigurację i zapisuje ją wraz z participant IDs; durable snapshot niesie
  ten sam scope; competitive detail przekazuje manifest participant IDs do
  scoringu i agregacji ceny; internal detail używa runtime price summary
  zamiast stałego `no_data`.
- Dodano regresje `scoped_commit_payload` dla mieszanego 2w1/3w1 oraz testy
  kontraktów detail przekazujące manifest scope i ceny internal. Zmieniono
  `scripts/run_model_research_pipeline.py`, `fieldnote-api/app.py`,
  `fieldnote-api/services/benchmark_commit_service.py` i testy Unit 8.
- Weryfikacja: focused pipeline/snapshot suite — **10 PASS**; kompilacja
  wszystkich zmienionych modułów i testów — PASS. Uruchomienie testów API w
  `fieldnote-api/.venv` zatrzymało się na istniejącym odczycie dużego corpus;
  pełny `check_fieldnote.sh` nie został oznaczony jako PASS z powodu znanego
  zawieszenia hygiene na `git show :<tracked-path>`.
- Status: **partial**, oczekuje ograniczonego re-review Unit 8. Nie rozpoczęto
  Unit 8.5 ani Unit 9. Następny krok:
  `$dev-docs-review docs/active/fieldnote-stroller-mvp 8`.

### Unit 8 — ograniczony re-review `f5fca8c^..f5fca8c` (`2026-08-06`)

- Zakres obejmował tylko remediation ostatnich findings Unit 8. Niezależnie
  użyto `correctness_reviewer`, `security_reviewer`, `test_reviewer` i
  `data_reviewer`; UI review nie był wymagany. Nie zmieniano kodu ani nie
  rozpoczęto Unit 8.5/9.
- Security: PASS. Skonsolidowano 2 P1: brak konfiguracji w normalnym job/run
  handoff i wspólna durable tożsamość benchmark_group oraz competitive detail
  z anchorem Lionelo wybierający internal cohort zamiast manifestu.
- Przyjęto 2 P2: realny pipeline nie dostarcza ceny do internal summary, a
  nowy test API kończy się `NameError` i mockuje kluczową ścieżkę.
- Weryfikacja: pipeline/snapshot — 10 PASS; zmienione testy API — 2 PASS,
  1 ERROR; `py_compile` i `git diff --check f5fca8c^..f5fca8c` — PASS.
  Pełny offline gate nadal nie kończy hygiene w tym środowisku.
- Gate: **BLOKUJE** — 2 P1, 2 P2, 0 P3. Następny krok: naprawić wyłącznie
  checkboxy Unit 8 z sekcji „Do poprawy po review”, potem ograniczony re-review.

### Unit 8 — wykonanie remediation po re-review (`2026-08-06`)

- Naprawiono wyłącznie cztery findings z `review-unit-8.md`: konfiguracja jest
  propagowana przez `product_scope`/job context z fallbackiem katalogowym;
  durable benchmark-group snapshot ma identity `benchmark_group::configuration`;
  competitive runtime przyjmuje jawny tryb manifestu także dla anchora Lionelo;
  internal price agreguje group offers oraz canonical linked source projection.
- Naprawiono strukturę testu API i dodano niemockowane fixtures: manifestowy
  participant+price scope, realne ceny internal, mismatch 2w1/3w1 oraz
  konfiguracyjnie partycjonowany snapshot.
- Weryfikacja: focused API remediation **6 PASS**, pipeline/snapshot
  remediation **3 PASS**, wcześniejsza suite Unit 8 **10 PASS**; py_compile i
  `git diff --check` PASS. Pełny `bash scripts/check_fieldnote.sh` ponownie
  zatrzymał się na `tests/test_repository_hygiene.py` podczas `git show
  :<tracked-path>` i został przerwany, więc nie oznaczam pełnego gate jako PASS.
- Status: **partial**, oczekuje ograniczonego re-review wyłącznie tych zmian.
  Unit 8.5 i Unit 9 nie zostały rozpoczęte. Następny krok:
  `$dev-docs-review docs/active/fieldnote-stroller-mvp 8`.

### Unit 8 — końcowy ograniczony re-review `ab1941d^..ab1941d` (`2026-08-06`)

- Zakres: wyłącznie config scope, competitive manifest mode, internal price
  source oraz regresje z commitu `ab1941d`. Correctness, security i data
  review: PASS. Test reviewer nie odpowiedział w dostępnej fali, więc zakres
  testowy zweryfikowano jako single-agent fallback przez wykonanie focused
  suites; nie zmieniano kodu ani nie rozpoczęto Unit 8.5/9.
- Weryfikacja: focused API runtime **6 PASS**, scoring/pipeline/snapshots
  **38 PASS**, `py_compile` i `git diff --check ab1941d^..ab1941d` — PASS.
  Pełny offline gate pozostaje nieukończony przez istniejące zawieszenie
  hygiene na `git show :<tracked-path>`.
- Gate: **GOTOWE DO KONTYNUACJI** — 0 P1, 0 P2, 0 P3. Unit 8 jest ukończony;
  dokument źródłowy wyniku: `review-unit-8.md`.

### Unit 8.5 — wykonanie częściowe (`2026-08-06`)

- Dodano `ProductRefreshService` jako dependency-injected kontrakt dla jednego
  produktu. Każde wywołanie wykonuje świeży Search i Scrape bez cache/resume,
  odrzuca niezgodne listingi przed pobraniem, zapisuje raw/clean obiekty przed
  historią źródła i deduplikuje snapshot po `(source_id, content_hash)`.
- Dodano migrację `202608060001_product_refresh_history.sql` z historią runów,
  relacją run–source, unikalnością snapshotu i prywatnymi politykami RLS.
- Offline testy: **4 PASS** (`tests/test_product_refresh_pipeline.py`),
  `py_compile` i `git diff --check` PASS. Nie wywołano Firecrawl/OpenAI.
- Próba pełnego `bash scripts/check_fieldnote.sh` została przerwana po 20 s;
  istniejąca bramka zatrzymuje się w hygiene na odczycie `git show
  :<tracked-path>`, więc nie oznaczam pełnego gate jako PASS.
- Poza zakresem tej części implementacji pozostają: podłączenie do durable
  job/worker, produkcyjny Storage adapter, deterministyczna ekstrakcja pól i
  ograniczone OpenAI, fenced incremental commit oraz pełne RLS/integration
  tests. Unit 8.5 ma status **partial**; Unit 9 nie rozpoczęto.

### Unit 8.5 — pełny review `447673f..7ef02e5` (`2026-08-06`)

- Review wykonali niezależnie `correctness_reviewer`, `security_reviewer`,
  `test_reviewer` oraz, z racji migracji/provenance, `data_reviewer`. Nie
  zmieniano kodu ani nie rozpoczęto Unit 9.
- Weryfikacja: 11 focused testów offline PASS, `py_compile` i
  `git diff --check 447673f..7ef02e5` PASS. Pełny offline gate nie ukończył się
  przez istniejące zawieszenie hygiene na `git show :<tracked-path>`.
- Gate: **BLOKUJE** — 3 P1, 5 P2, 0 P3. Kluczowe braki to niewpięty durable
  flow, nieobsługiwany realny `FirecrawlResponse` oraz brak relacji drugiego
  identycznego runu do deduplikowanego snapshotu. Szczegóły:
  `review-unit-8.5.md`. Unit 8.5 pozostaje **partial**.

### Unit 8.5 — remediation częściowa (`2026-08-06`)

- Poprawiono obsługę obiektowego `FirecrawlResponse`, walidację HTTPS i
  allowlistę Allegro przed scrape, kanoniczny prefiks `allegro:` dla ofert,
  jawny znacznik create/reuse zamiast tożsamości obiektu oraz wersjonowanie raw
  artefaktu po payload hash. Dodano pamięciowe relacje run-source i migrację
  rozdzielającą snapshot od asocjacji runu.
- Weryfikacja: **14 focused testów PASS**, `py_compile` i `git diff --check`
  PASS. Nie wywołano płatnych API.
- Nadal nie podłączono serwisu do API/durable worker/jobów i produkcyjnego
  repozytorium Storage/źródeł, nie ma wykonawczego RLS testu ani transakcyjnego
  FK upsertu. Unit 8.5 pozostaje **partial**; nie rozpoczynano Unit 9.

### Unit 8.5 — ograniczony re-review `7ef02e5..cf6e2ed` (`2026-08-06`)

- Użyto niezależnie `correctness_reviewer`, `security_reviewer`,
  `test_reviewer` i `data_reviewer`; review objął wyłącznie ostatni commit
  remediation i poprzednie findings. Nie zmieniano kodu ani nie rozpoczęto
  Unit 9.
- Weryfikacja: focused refresh/Firecrawl suite **14 PASS**, `py_compile` i
  `git diff --check 7ef02e5..cf6e2ed` PASS.
- Gate: **BLOKUJE** — 2 P1, 5 P2, 0 P3. Zamknięto problem formatu
  `FirecrawlResponse` i deduplikacji opartej o tożsamość obiektu. Pozostają
  trwały API→worker flow, persistowalny snapshot ID i pięć P2 z
  `review-unit-8.5.md`. Unit 8.5 ma status **partial**.

### Unit 8.5 — remediation po re-review (`2026-08-06`)

- Dodano typed `product_refresh` do payloadu jobu i endpointu jobs, branch
  workera omijający legacy `--resume`, adapter Supabase Storage/history oraz
  kontrakt snapshot UUID + per-run raw/clean paths. Dodano testy payloadu jobu
  i terminalizacji workera na fixture.
- URL allowlista jest wykonywana przed custom identity gate; źródła Allegro są
  kanonizowane, a migracja ma trzy tabele historii z relacją snapshot →
  run-source. Schema/RLS contracts obejmują nowe tabele.
- Weryfikacja: **32 focused testy PASS**, `py_compile` i `git diff --check`
  PASS. Runtime PostgREST/RLS, evidence/candidates, OpenAI i fenced scoped
  commit pozostają do dokończenia. Unit 8.5 ma status **partial**.

### Unit 8.5 — ograniczony re-review `cf6e2ed..0c8ec07` (`2026-08-06`)

- Sprawdzono wyłącznie ostatnią remediation. Correctness uruchomiono jako
  subagenta; security/tests/data wykonano jako single-agent fallback z powodu
  limitu subagentów. Nie zmieniano kodu ani Unit 9.
- Weryfikacja: 32 focused testy PASS, `py_compile` i `git diff --check` PASS.
  Pełny offline gate nadal zatrzymuje hygiene po 20 s.
- Gate: **BLOKUJE** — 2 P1, 2 P2. Worker zamienia udany refresh bez envelope w
  failed po zapisaniu side effects; brakuje ekstrakcji/evidence/scoped commit,
  limitów/cancel i runtime RLS testu. Szczegóły w `review-unit-8.5.md`.

### Unit 8.5 — remediation `0c8ec07..HEAD` (`2026-08-06`)

Serwis przyjmuje limity i `cancel_check`, ogranicza Search oraz sprawdza
anulowanie przed każdym Scrape. Snapshot zwraca evidence/excerpt i kandydata
pola. Worker mapuje refresh bez `scoped_commit` na `partial/no_mutation`, bez
fałszywego `failed` po zapisaniu źródeł. 32 focused testy, py_compile i diff
check PASS; pełny gate zatrzymał się na znanym zawieszeniu hygiene. Nadal
brakuje pełnych faktów/OpenAI, fenced scoped commit i runtime RLS. Unit 8.5
pozostaje **partial**; Unit 9 nie rozpoczęto.
