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

## Blokery i ryzyka

- Runtime Supabase działa; ostatni P2 jest naprawiony i oczekuje ograniczonego re-review.
- Istniejące lokalne dane, outputy i środowiska nie mogą trafić do repo.
- Live provider calls i koszty są poza automatyczną weryfikacją.

## Przekazanie

- **Bieżący unit:** Unit 2 — Supabase schema, Auth, Storage i RLS
- **Status:** partial — naprawiono ostatni P2; Unit 2 oczekuje ograniczonego re-review.
- **Pliki w toku:** `tests/test_supabase_runtime_contract.py`, `review-unit-2.md` i aktywne dokumenty Unit 2.
- **Ostatnie testy:** runtime test 5 PASS; kontrakty schema/RLS/runtime 14 PASS (5 opt-in skipped); pełny offline gate PASS; `git diff --check` PASS.
- **Bloker:** oczekujący ograniczony re-review ostatniej poprawki P2; nie rozpoczynać Unit 3.
- **Następny krok:** ograniczony `$dev-docs-review docs/active/fieldnote-stroller-mvp 2` wyłącznie dla adminowego testu katalogu.
