# FIELDNOTE Stroller MVP — zadania

- **Branch:** `main` (czyste i zsynchronizowane z `origin/main` przed Unit 2)
- **Ostatnia aktualizacja:** 2026-07-28

## Unit 1 — Bezpieczny baseline repozytorium i CI

- [x] Implementacja: `.gitignore`, trzy `.env.example`, GitHub CI/Dependabot, `docs/SECURITY_BASELINE.md` oraz offline check bez sekretów, lokalnych danych, snapshotów, runów i środowisk w indeksie.
- [x] Test: `tests/test_repository_hygiene.py` odrzuca śledzone `.env`, klucze, bazy, produkcyjne snapshoty i katalogi środowisk.
- [x] Weryfikacja: `scripts/check_fieldnote.sh` przechodzi bez Firecrawl/OpenAI; hygiene test nie znajduje sekretów ani artefaktów w indeksie.
- [ ] Operator: właściciel tworzy prywatne repo GitHub i rotuje klucze, które mogły znaleźć się w archiwum lub lokalnym env.
- [x] Review: PASS; brak otwartych P1/P2. Szczegóły w `review-unit-1.md`.

## Unit 1.5 — Repository cleanup

- [x] Audyt: root sklasyfikowany w `repository-cleanup-plan.md`; potwierdzone aktywne ścieżki Streamlit, FastAPI, React/Vite, pipeline i testów.
- [x] Plan: zapisano strukturę docelową, listę keep/move/delete, ryzyka, ścieżki wymagające audytu i weryfikację.
- [x] Bezpieczne działania: cache/lokalne środowiska usunięte, ZIP-y diagnostyczne oraz `project_files.txt` zarchiwizowane poza aktywnym kodem.
- [x] Weryfikacja: targety cleanup nie istnieją; hygiene test nie znajduje artefaktów w indeksie.
- [ ] Review: wymagany po zakończeniu bezpiecznych działań.

## Unit 2 — Supabase schema, Auth, Storage i RLS

- [x] Implementacja: migracje core catalog/source/benchmark/jobs/auth-RLS-storage, idempotentny seed oraz prywatne buckety `source-raw`, `source-clean`, `imports`.
- [x] Test: kontrakty schema/RLS oraz opt-in `tests/test_supabase_runtime_contract.py` pokrywają anon/viewer/analyst/admin przez PostgREST, API Storage, spoofing aktora, spójność evidence także po update linku, unikalny aktywny job, współdzielone source ID i stabilne UUID obu seedów.
- [x] Weryfikacja: `supabase db reset` PASS; kontrakty schema/RLS/runtime PASS (14 testów, 5 opt-in skipped), runtime z integracją PASS (5), pełna offline bramka `bash scripts/check_fieldnote.sh` PASS oraz `git diff --check` PASS.
- [x] Review: PASS po ograniczonym re-review — brak otwartych P1/P2. Szczegóły w `review-unit-2.md`.

## Unit 3 — Repozytoria Supabase i selektywna migracja

- [x] Implementacja: repozytoria catalog/source/benchmark/job/audit, stdlib klient Supabase i selektywna migracja wersjonowanego fixture z trybem `legacy_readonly`; tryb `supabase` fail-closed wymaga serwerowej konfiguracji.
- [x] Test: `tests/test_supabase_repositories.py`, `tests/test_selective_migration.py` oraz kontrakty API; 34 Lionelo, brak placeholdera, idempotencja migracji, poprawne links/evidence i odrzucenie złych referencji.
- [x] Weryfikacja: audit migracji raportuje selekcję/odrzucenia; `/api/products` w trybie `supabase` czyta wstrzyknięte repozytorium bez odwołania do legacy katalogu lub danych generowanych.
- [x] Review: PASS po ograniczonym re-review — brak otwartych P1/P2. Szczegóły w `review-unit-3.md`.

## Unit 4 — Logowanie, role i administracja kontami

- [x] Implementacja: FastAPI dependencies/role/auth/admin-users oraz frontendowa sesja Supabase, guardy i ekrany logowania/zmiany hasła/użytkowników.
- [x] Test: `tests/test_auth_roles.py`, `fieldnote-frontend/tests/auth-guards.test.mjs`; 401/403 i role viewer/analyst/admin.
- [x] Weryfikacja: backend/frontend testy i pełny offline gate przechodzą; browser flow wymaga ręcznego skonfigurowania Supabase.
- [x] Review: PASS po ograniczonym re-review; brak otwartych P1/P2. Szczegóły w `review-unit-4.md`.
- [x] Zależność: oficjalny `@supabase/supabase-js` (v2.110.8) dodany przez `pnpm`; nie używać własnego klienta sesji.
- [x] Naprawa po review: wszystkie trasy API w trybie Supabase poza health/auth wymagają sesji; zmiana hasła jest serwerowo powiązana ze zdjęciem flagi; dodano focused regresje auth.
- [x] Naprawa po re-review: centralna polityka odrzuca mutacje viewer; `TestClient` wykonawczo pokrywa anon, viewer, analyst, admin i wymuszoną zmianę hasła.
- [x] Re-review: `efd5ab5^..efd5ab5` zamknął ostatni P2; Unit 4 ma PASS i brak otwartych P1/P2.

## Unit 5 — Kolejka PostgreSQL i worker z dwoma slotami

- [x] Implementacja: migracja queue z RPC `SKIP LOCKED`/lease/heartbeat, `JobService`, worker, router `/api/jobs`, adapter legacy CLI i cancellation control file; UI enqueue/poll/cancel czyta trwałe joby.
- [x] Test: `tests/test_postgres_job_queue.py`, `tests/test_worker_leases.py`, `tests/test_job_cost_limits.py`, `fieldnote-frontend/tests/run-status.test.mjs` oraz kontrakt historii durable jobów.
- [x] Weryfikacja: pełny offline gate potwierdza ograniczenie do dwóch slotów w RPC, fencing lease, odrzucenie duplikatu aktywnego produktu, odzyskanie wygasłego lease w kontrakcie SQL, cancel przed wykonaniem i `partial` po limicie.
- [ ] Review: `WYMAGA POPRAWEK` — 0 P1, 1 P2, 0 P3; szczegóły w `review-unit-5.md`.

## Unit 6 — Przyrostowe commitowanie i przeliczanie

- [ ] Implementacja: `product_scope`, `benchmark_group_scope`, rebuild pojedynczego scope'u i serializowany admin full rebuild.
- [ ] Test: `tests/test_incremental_pipeline.py`, `tests/test_incremental_benchmark_rebuild.py`; niepowiązane produkty pozostają niezmienione, snapshot powstaje dopiero przy istotnej zmianie.
- [ ] Weryfikacja: suma przyrostowych rebuildów daje stan równy full rebuild na fixture.
- [ ] Review: brak otwartych P1/P2.

## Unit 7 — Wspólny Firecrawl i katalog konkurencji

- [ ] Implementacja: wspólny klient v2, adaptery, discovery katalogu producenta, aliasy, konfiguracja źródeł oraz fixtures dla manufacturer/Allegro/Amazon/retailers.
- [ ] Test: `tests/test_firecrawl_client.py`, `tests/test_firecrawl_source_adapters.py`, `tests/test_manufacturer_catalog_discovery.py`, `tests/test_product_aliases.py`.
- [ ] Weryfikacja: adapter tests przechodzą offline; raport nie ma aktywnego `Accessory / part` ani niejawnie niesklasyfikowanego realnego produktu.
- [ ] Review: brak otwartych P1/P2.

## Unit 8 — Audyt atrybutów i względny scoring

- [ ] Implementacja: wersjonowany schema wózków, audyt 21 pól, scoring względny, internal/competitive benchmark i agregacja cen.
- [ ] Test: atrybuty, normalizacja, scoring, ceny i semantyczne snapshoty bez AI.
- [ ] Weryfikacja: każdy z 21 atrybutów ma decyzję; cztery grupy dają benchmark albo jawny powód braku uczestników.
- [ ] Review: brak otwartych P1/P2.

## Unit 9 — UI produkcyjne i import administratora

- [ ] Implementacja: import XLSX preview/commit, ekrany produktów, benchmarków, źródeł, runów i researchu przez API.
- [ ] Test: import API/preview oraz frontendowe testy importu, benchmarków i flow jobu.
- [ ] Weryfikacja: typecheck/test/build i browser flow importu, researchu, benchmarku oraz źródeł; brak runtime importów `src/data/generated`.
- [ ] Review: brak otwartych P1/P2.

## Unit 10 — Render i security gate

- [ ] Implementacja: Render/Docker/static/CI deploy configs, e2e env, deployment/security/runbook docs i health readiness.
- [ ] Test: konfiguracja deploymentu i security headers.
- [ ] Weryfikacja: CI, migrations, seed oraz E2E na dedykowanym środowisku; worker odbiera fixture job.
- [ ] Operator: projekty Supabase, sekrety Render, MFA i limitowany staging live run.
- [ ] Review: brak otwartych P1/P2.

## Unit 11 — Zamknięcie danych MVP

- [ ] Implementacja: closure/audit scripts, raport zamknięcia oraz aktualizacja statusu, README i operacji.
- [ ] Test: closure odrzuca katalog niezgodny z 34 Lionelo, niejawnych konkurentów i benchmarki między grupami.
- [ ] Weryfikacja: audit PASS oraz raport z liczbami katalogu, źródeł, benchmarków, runów i bezpieczeństwa.
- [ ] Review: brak otwartych P1/P2.

## Do poprawy po review

<!-- Dodawaj findings pod właściwym unitem. -->

### Unit 1

- [x] P2: CI instaluje zależności API przed uruchomieniem pełnej offline bramki.
- [x] P2: hygiene test skanuje staged blob zamiast zawartości worktree.
- [x] P2: fixture regresji nie może zawierać w śledzonym pliku literalnego sekretu rozpoznawanego przez hygiene scanner.

### Unit 2

- [x] P2: wymuszono w `audit_events` aktora równego `auth.uid()` i dodano regresję JWT analityka dla spoofingu `actor_id`.
- [x] P2: wymuszono spójność `evidence_items.product_id`, `source_id` i `product_source_link_id`; dodano regresję odrzucającą mismatch.
- [x] P2: zablokowano zmianę `product_id`/`source_id` użytego `product_source_link`; runtime regresja odrzuca update linku.
- [x] P2: dodano wykonawcze requesty PostgREST/API dla anon, viewer, analyst i admin na tabelach RLS (obok helperów/Storage).
- [x] P2: seed runtime test porównuje stabilne UUID dev i E2E po drugim uruchomieniu.
- [x] P2: dodano wykonawczy zapis katalogu przez PostgREST jako admin oraz odmowę analogicznej akcji dla analyst.
- [x] P2: wykonano dwukrotny adminowy POST/UPSERT `brands` przez PostgREST i potwierdzono stabilną pojedynczą pozycję fixture.

### Unit 3

- [x] P1: zmapowano kanoniczny katalog Lionelo (`scope=production`, `refresh_recommended`, brak `is_lionelo`) do kontraktu `products`; fixture obejmuje 34 produktów.
- [x] P2: w Supabase `POST /api/products` używa repozytorium bez legacy odczytu/zapisu i zachowuje rekord w list/detail.
- [x] P2: detail w Supabase nie odczytuje legacy provenance.
- [x] P2: dodano wersjonowany fixture oraz wykonywalny entrypoint migracji i audytu.
- [x] P2: audit wymaga dokładnie 34 distinct produktów Lionelo, niezależnie od konkurentów i duplikatów.
- [x] P1: fixture/audit używa dokładnego zatwierdzonego zbioru 34 realnych Lionelo ze śledzonych specyfikacji, nie syntetycznych `00..33`.
- [x] P1: zapis katalogu przez API z service-role jest wyłączony w Unit 3 do czasu autoryzacji Unit 4.
- [x] P2: ujednolicono `brand_key` dla nazw wielowyrazowych i dodano regresję.
- [x] P2: CLI audit nie ufa `expected_lionelo_product_ids` z wejściowego fixture; zawsze weryfikuje kanoniczny zbiór specs.
- [x] P2: migracja waliduje kanoniczny zbiór Lionelo przed pierwszym upsertem; fixture niezgodny z `data/internal_specs` nie może wykonać zapisu.
- [x] P2: test CLI z niekanonicznym fixturem potwierdza kod 2 przed utworzeniem `SupabaseClient` i repozytoriów.

### Unit 4

- [x] P1: wszystkie metody mutujące API w trybie Supabase wymagają roli analyst lub admin; viewer zachowuje tylko odczyt.
- [x] P1: endpoint zmiany hasła aktualizuje hasło przez serwerowy Auth Admin przed zdjęciem `must_change_password`.
- [x] P2: macierz HTTP `TestClient` wykonawczo sprawdza anon, viewer, analyst, admin, wymaganie zmiany hasła i odmowę mutacji viewer.
- [x] P1: flow frontendowy wymuszonej zmiany hasła przekazuje nowe hasło do `POST /api/auth/change-password`; po potwierdzeniu backendu odświeża profil bez pozostawienia użytkownika na ekranie zmiany hasła.
- [x] P2: klient zmiany hasła akceptuje wyłącznie literalne `must_change_password: false`; odpowiedź brakująca, `null` lub `true` nie może odświeżać profilu ani sygnalizować sukcesu.

### Unit 5

- [x] P1/P2: wdrożono poprawki z review Unit 5 (RLS kolejki, heartbeat/fencing, immutable context, limity/cancel, recovery, event mapping, total/pagination, polling i DTO).
- [x] P2: wykonawczy lokalny test PostgreSQL concurrency/RLS używa realnych RPC/PostgREST, równoległych claimów, recovery/fencing oraz odmowy DML anon/analyst.
- [x] Weryfikacja: runtime Supabase 6 testów PASS, focused backend 32 testy PASS, `git diff --check` PASS; offline gate i frontend pozostają zielone.
- [x] P2: wyścig o pojedynczy queued job asercją obejmuje wszystkie odpowiedzi claimantów i wymusza dokładnie jeden lease.
- [x] P2: stale token jest wykonawczo odrzucony przez `fieldnote_start_research_job`, a bieżący token może przejść do `running`.
- [x] P2: po terminalizacji wygasłego anulowanego joba test tworzy kolejny job dla tego samego produktu, dowodząc zwolnienia blokady.
- [x] P2: runtime PostgreSQL odrzuca drugi aktywny job tego samego produktu przed cancel recovery, a po terminalizacji przyjmuje nowy job.
- [ ] Review: implementacja poprawki zakończona; oczekuje ograniczony re-review P2. Unit 6 nie rozpoczęto.
