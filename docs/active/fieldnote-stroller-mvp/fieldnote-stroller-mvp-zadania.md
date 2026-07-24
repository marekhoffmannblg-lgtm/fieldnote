# FIELDNOTE Stroller MVP — zadania

- **Branch:** `main` (czyste i zsynchronizowane z `origin/main` przed Unit 2)
- **Ostatnia aktualizacja:** 2026-07-24

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

- [ ] Implementacja: repozytoria catalog/source/benchmark/job/audit, klient Supabase i migracja zatwierdzonego legacy state z trybem `legacy_readonly`.
- [ ] Test: `tests/test_supabase_repositories.py`, `tests/test_selective_migration.py`; 34 Lionelo, brak placeholdera i idempotencja migracji.
- [ ] Weryfikacja: audit migracji nie wykazuje niejawnej utraty poprawnych source links; API czyta katalog z Supabase.
- [ ] Review: brak otwartych P1/P2.

## Unit 4 — Logowanie, role i administracja kontami

- [ ] Implementacja: FastAPI dependencies/role/auth/admin-users oraz frontendowa sesja Supabase, guardy i ekrany logowania/zmiany hasła/użytkowników.
- [ ] Test: `tests/test_auth_roles.py`, `fieldnote-frontend/tests/auth-guards.test.mjs`; 401/403 i role viewer/analyst/admin.
- [ ] Weryfikacja: browser flow logowania, wymuszonej zmiany hasła i blokady viewer przechodzi.
- [ ] Review: brak otwartych P1/P2.

## Unit 5 — Kolejka PostgreSQL i worker z dwoma slotami

- [ ] Implementacja: job/pipeline services, router, worker, lease oraz koszty i anulowanie w PostgreSQL.
- [ ] Test: `tests/test_postgres_job_queue.py`, `tests/test_worker_leases.py`, `tests/test_job_cost_limits.py`, `fieldnote-frontend/tests/run-status.test.mjs`.
- [ ] Weryfikacja: dwa sloty bez podwójnego jobu; status odtwarzalny po restarcie API/workera.
- [ ] Review: brak otwartych P1/P2.

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
