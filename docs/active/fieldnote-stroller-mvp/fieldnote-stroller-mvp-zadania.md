# FIELDNOTE Stroller MVP — zadania

- **Branch:** `main` (czyste i zsynchronizowane z `origin/main` przed Unit 2)
- **Ostatnia aktualizacja:** 2026-07-30

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
- [x] Review: PASS po ograniczonym re-review `8fa7fd4..b59d169`; brak otwartych P1/P2. Szczegóły w `review-unit-5.md`.

## Unit 6 — Przyrostowe commitowanie i przeliczanie

- [x] Implementacja: `product_scope`, `benchmark_group_scope`, rebuild pojedynczego scope'u i serializowany admin full rebuild.
- [x] Test: `tests/test_incremental_pipeline.py`, `tests/test_incremental_benchmark_rebuild.py` oraz opt-in `tests/test_supabase_runtime_contract.py`; direct CLI, dwa scope'y/admin, price threshold, stale rows i fenced RPC.
- [x] Weryfikacja: suma rebuildów przyrostowych daje stan równy full rebuild na fixture; focused 30 PASS, opt-in runtime Unit 6 (RPC i upgrade migracji) 2 PASS, pełny offline gate PASS.
- [x] Review: PASS po ograniczonym re-review `395abc9..c3646b7`; brak otwartych P1/P2. Szczegóły w `review-unit-6.md`.

## Unit 7 — Wspólny Firecrawl i katalog konkurencji

- [x] Implementacja: wspólny klient v2, adaptery, discovery katalogu producenta, aliasy, konfiguracja źródeł oraz fixtures dla manufacturer/Allegro/Amazon/retailers.
- [x] Test: `tests/test_firecrawl_client.py`, `tests/test_firecrawl_source_adapters.py`, `tests/test_manufacturer_catalog_discovery.py`, `tests/test_product_aliases.py` oraz remediation regressions — 28 PASS.
- [x] Weryfikacja: adapter tests przechodzą offline; raport katalogu nie zawiera aktywnego `Accessory / part` ani niejawnie niesklasyfikowanego realnego produktu; pełny `bash scripts/check_fieldnote.sh` PASS.
- [x] Review: PASS po ograniczonym re-review `360972e^..360972e`; brak otwartych P1/P2. Szczegóły w `review-unit-7.md`.

## Unit 8 — Audyt atrybutów i względny scoring

- [x] Implementacja: wersjonowany schema wózków, audyt 21 pól, scoring względny, internal/competitive benchmark i agregacja cen.
- [x] Implementacja remediation: runtime endpointy i scoped snapshot projection używają scoringu/ceny; brak danych nie zaniża utility score; konfiguracja, `suspension`, aliasy i konwersje są deterministyczne.
- [x] Test: atrybuty, aliasy, normalizacja, scoring, ceny, konfiguracja, corpus 34 i semantyczne snapshoty bez AI — 20 PASS.
- [ ] Weryfikacja: focused i py_compile przechodzą; pełny `bash scripts/check_fieldnote.sh` zatrzymuje się na `test_repository_hygiene.py`/`git show`, a testy FastAPI wymagają środowiska z zależnością `fastapi`.
- [x] Review: PASS po ograniczonym re-review `ab1941d^..ab1941d`; brak otwartych P1/P2. Szczegóły w `review-unit-8.md`.

## Unit 8.5 — Trwałe, pełne odświeżenie danych produktu

- [ ] Implementacja: fundament offline istnieje, lecz brakuje durable API/job/worker/Storage, poprawnej relacji run-source-snapshot, ekstrakcji i fenced incremental commit.
- [ ] Test: focused API/worker i schema/RLS contracts przechodzą; brakuje wykonawczego PostgREST/RLS runtime, limitów/cancel/lease i pełnej historii po restarcie.
- [ ] Weryfikacja: dwa identyczne refresh runy pozostają w historii, lecz nie duplikują source/semantic snapshots; zmiana obejmuje wyłącznie produkt i jego istniejący scope benchmarkowy.
- [ ] Operator: jeden limitowany live smoke produktu dopiero poza CI, bez masowego refreshu.
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

### Unit 8.5 — pełny review `447673f..7ef02e5`

- [x] P1: podłączyć typed `product_refresh` przez router, trwałą kolejkę,
  worker i repozytoria/Storage; branch workera omija legacy `--resume`.
  Fenced scoped commit pozostaje do integracji.
- [x] P1: obsłużyć `FirecrawlResponse.data` wspólnego klienta i dodać test
  refreshu z jego fixture transportem.
- [x] P1: rozdzielić deduplikowany snapshot od per-run source association;
  produkcyjny adapter zwraca snapshot UUID i przekazuje go do linku runu.
- [x] P2: zastąpić deduplikację opartą o `is` jawnym wynikiem create/reuse.
- [x] P2: normalizować/upsertować kanoniczne `allegro:<offer_id>` wraz z linkiem
  produktu przed insertem historii; runtime FK test pozostaje do wykonania.
- [x] P2: walidować HTTPS allowlist URL-i przed scrape także dla wstrzykniętego
  identity gate i odrzucać prywatne/obce hosty.
- [x] P2: wersjonować raw artefakt po hash payloadu, aby nie nadpisywać evidence
  przy tym samym clean content.
- [ ] P2: dodać opt-in wykonawczy PostgREST/RLS test nowych tabel historii.

### Unit 8.5 — ograniczony re-review `cf6e2ed..0c8ec07`

- [ ] P1: refresh ma kończyć workerowy flow fenced `scoped_commit` albo
  kontrolowanym partial/no-mutation; nie może być później zmieniany na failed.
- [ ] P1: po refreshu zapisać deterministyczne fakty, evidence/candidates i
  scoped benchmark update, z OpenAI wyłącznie dla braków/niejednoznaczności.
- [ ] P2: przekazać limity/cancel/usage jobu do Search/Scrape i zwracać partial
  lub cancelled bez przekroczenia budżetu.
- [ ] P2: uruchomić opt-in lokalny PostgREST/Storage RLS test historii refreshu.

### Unit 8.5 — ograniczony re-review `0c8ec07..8b766a5`

- [ ] P1: utrwalać kanoniczną `configuration` w typed job payload i wymuszać ją w discovery/identity refreshu.
- [ ] P1: egzekwować timeout i cancellation także w trakcie/po wywołaniu providera; anulowanie ma kończyć się `cancelled`.
- [ ] P1: dokończyć deterministyczną ekstrakcję faktów, ograniczone OpenAI i fenced scoped commit tylko dla istniejącego scope produktu.
- [ ] P2: dodać regresję workerową typed refresh `partial/no_mutation`, pozytywny `max_pages` i anulowanie między dwoma Scrape.
- [ ] P2: uruchomić opt-in lokalny PostgREST/Storage RLS test historii refreshu.

### Unit 8 — ograniczony re-review `f5fca8c^..f5fca8c`

- [x] P1: propagować kanoniczną konfigurację przez job/run context i
  partycjonować durable benchmark snapshot/RPC per `benchmark_group + configuration`.
- [x] P1: competitive detail z anchorem Lionelo ma używać dokładnie manifestowych
  competitor participants dla scoringu oraz price observations, nie internal cohort.
- [x] P2: zasilić internal price summary realnymi price observations pipeline,
  nie tylko nieobecnym polem w `group.json`.
- [x] P2: naprawić czerwony test API i dodać niemockowane regresje scope
  manifestu, ceny internal oraz HTTP 422 dla 2w1 ↔ 3w1.

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

### Unit 8

- [x] P1: podłączyć scoring, ceny i semantic snapshoty do endpointów oraz przyrostowego commitu runtime.
- [x] P1: liczyć utility score wyłącznie z wag prawidłowych pól danego produktu; brak ma obniżać tylko completeness.
- [x] P2: wymusić zgodność konfiguracji w internal benchmarku i competitive manifeście.
- [x] P2: naprawić boolean/deterministyczną normalizację scored pola `suspension`.
- [x] P2: dodać do schema aliasy PL/EN oraz wersjonowane konwersje i normalizację kluczy.
- [x] P2: dodać regresje rankingu, granic participantów/konfiguracji, mediany/recency cen oraz audytu corpus 34 specyfikacji.
- [x] P1: scoped semantic benchmark i durable snapshot filtrują dokładnie konfigurację produktu researchu oraz zapisują ją wraz z participant IDs.
- [x] P1: detail competitive benchmarku liczy score i cenę dokładnie dla anchora oraz `participant_product_ids` zapisanego manifestu.
- [x] P2: internal benchmark detail agreguje ceny dokładnego participant scope zamiast raportować stałe `no_data`.
- [x] P2: dodano wykonawcze regresje scope konfiguracji, manifest participant set, cen internal i snapshot scope; pełna suite API nadal wymaga osobnego uruchomienia w venv.
- [x] P1/P2 remediation: konfiguracja jest propagowana z katalogu przez job context i legacy fallback, durable group snapshot ma scope per konfiguracja, competitive runtime ma jawny tryb manifestu, a internal price czyta także canonical linked source projection.
- [x] Testy remediation: API/runtime fixtures obejmują exact participant+price scope, internal medianę, config mismatch 422 oraz konfigurację snapshot scope.
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
- [x] Review: PASS po ograniczonym re-review `8fa7fd4..b59d169`; brak otwartych P1/P2. Unit 6 nie rozpoczęto.

### Unit 6

- [x] P1: kanoniczny CLI zawsze wylicza scope produktu i przekazuje `--group-key`; globalny rebuild pozostaje wyłącznie w jawnym CLI admina.
- [x] P1: scoped read–merge–commit oraz admin full rebuild używają wspólnej transakcji locka fixture; test współbieżny zachowuje oba scope'y i adminowy rebuild.
- [x] P1: worker kończy sukces/partial wyłącznie przez fenced RPC Supabase, który atomowo zapisuje scoped semantic snapshoty i terminalizuje job.
- [x] P2: scoped benchmark/coverage usuwa stare wiersze dla żądanej grupy, gdy przestaje być benchmark-eligible.
- [x] P2: testy obejmują dwie grupy wewnętrzne, canonical `--group-key`, brak eksportu frontendu, izolację niepowiązanej grupy oraz próg ceny.
- [x] P1: durable envelope wylicza medianę ceny z oryginalnych źródeł przed projekcją; cena 5%+ tworzy snapshot.
- [x] P1: preflight/timeout bez semantic envelope jest terminalizowany jako `partial`, nie `failed`.
- [x] P2: wykonawczy canonical direct-CLI test bez `--run-context` wymaga scoped etapów 8–9.
- [x] P2: kontrolowany test nakładania się admin full rebuild i scoped read–merge–write zachowuje oba scope'y.
- [x] P2: opt-in runtime PostgreSQL test fenced RPC obejmuje 4,99%/5%, stale token i invalid envelope.
- [x] P2: integration test builderów obejmuje utratę eligibility i usunięcie benchmark/source rows.
- [x] P1: snapshot `benchmark_group` nie dziedziczy ceny produktu; powstaje wyłącznie z jawnej projekcji internal benchmarku, a brak projekcji pomija snapshot grupy. Regresje pokrywają próg 4,99%/5% i zmianę agregatu.
- [x] P1: historyczna migracja `202607290001` została przywrócona bez zmian; poprawiony RPC jest w sekwencyjnej migracji `202607300001_incremental_commit_partial_fixes.sql`, z kontraktem monotonicznego upgrade'u.
- [x] P2: test serializacji fixture używa hooków sekcji krytycznej i zdarzeń, wymuszając adminową próbę podczas zablokowanego scoped read–merge–write.
- [x] P2: wykonawczy lokalny test odtwarza bazę z już zastosowaną migracją `202607290001`, stosuje wyłącznie `202607300001` bez resetu i potwierdza poprawione RPC dla JSON snapshotu oraz no-mutation `partial`.

### Unit 7

- [x] P1: timeout/429 providerów kończą się retry i trwałym `error`/`partial`, bez `NameError` ani tracebacku fetchera.
- [x] P1: quality gate blokuje realne rekordy `review_required`, a raport bieżącego katalogu wylicza niesklasyfikowane modele.
- [x] P1: adminowy refresh używa skonfigurowanego oficjalnego URL producenta i wspólnego klienta albo zwraca kontrolowany błąd/partial.
- [x] P1: normalizacja aliasów ignoruje kolor i zachowuje 2w1/3w1 także dla title-only recordów.
- [x] P1: ścieżka manuala PDF nie zapisuje HTML/markdown jako `document.pdf` ani nie raportuje fałszywego sukcesu.
- [x] P2: adaptery odrzucają kartę innego modelu, która tylko wspomina target jako kompatybilny.
- [x] P2: API ogranicza `fixture_root` do repozytoryjnego katalogu fixtures po rozwiązaniu ścieżki.
- [x] P1: discovery z poprawnym HTTP, ale pustym lub nierozpoznanym payloadem, kończy się `partial`/`review`, nie `success`/`pass`.
- [x] P1: `--resume` dla manuala odrzuca istniejący `document.pdf` bez sygnatury `%PDF`; nie zwraca `resume_skipped_existing_source` dla starego HTML.
- [x] P2: test discovery obejmuje wyczerpany `FirecrawlError` dla skonfigurowanego URL i asercję kontrolowanego `partial`.
- [x] P2: testy obejmują symlink escape `fixture_root` oraz kontrakt routera 422 bez wycieku JSON.
- [x] P2: deduplikacja rekordów katalogu jest niezależna od kolejności wejścia; sprzeczne klasyfikacje wymagają `review`.
- [x] P1: trzy lub więcej duplikatów nie może skasować uprzednio wykrytego konfliktu `benchmark_group`; wszystkie permutacje wymuszają `review_required`.
- [x] P2: deduplikacja zachowuje pełny, deterministyczny `source_ids` z każdego singular `source_id` duplikatów.
- [x] P1: konflikt między równocześnie ustawionymi `benchmark_group` i `benchmark_group_key` na dowolnej karcie daje `review_required`, a nie zostaje ukryty przez wybór pierwszego pola; dodano testy permutacji i quality gate discovery.
- [x] Review: ograniczony re-review Unit 7 — PASS i 0 P1/P2 (`360972e^..360972e`).

### Unit 8.5 — remediation `0c8ec07..HEAD` (`2026-08-06`)

- [x] Worker refresh bez fenced envelope kończy kontrolowanym `partial/no_mutation`.
- [x] Limity kandydatów/stron i callback cancel są przekazywane przed Search/Scrape.
- [x] Snapshot zwraca deterministyczne evidence/excerpt i kandydata pola.
- [ ] Pełne fakty, ograniczone OpenAI, fenced scoped commit i runtime RLS.
- [x] 32 focused testy, py_compile i git diff --check PASS; pełny gate zatrzymuje znane zawieszenie hygiene.
- [ ] Review końcowy PASS.

### Unit 8.5 — ograniczony re-review `dd1df6a^..dd1df6a`

- [ ] P1: podłączyć do produkcyjnego workera metrowany adapter OpenAI z wersjonowanym schema i bezpłatnym fixture contractem.
- [ ] P1: odrzucać pustą, niekompletną lub błędnie typowaną odpowiedź AI jako `partial/no_mutation`.
- [ ] P1: agregować usage Firecrawl/AI i nie publikować snapshotu przy nieznanym usage.
- [ ] P2: dodać wykonawczą regresję `succeeded + usage_complete=False + scoped_commit` → fenced no-mutation.
- [ ] P2: dodać cancel po udanym fallbacku AI, tuż przed publikacją.
- [ ] P2: uruchomić opt-in lokalny PostgREST RLS dla historii refreshu.

### Unit 8.5 — końcowa remediation workflow

- [x] Produkcyjny worker przekazuje metrowany adapter OpenAI, a brak konfiguracji kończy się `partial/no_mutation`.
- [x] Pusta, niekompletna lub błędnie typowana odpowiedź AI nie publikuje snapshotu.
- [x] Usage Firecrawl/AI jest wymagane do semantic commit; nieznane usage daje partial.
- [ ] Uruchomić lokalny Supabase RLS runtime i końcowy review PASS.

### Unit 8.5 — ograniczony re-review `54e7a05^..54e7a05`

- [x] P1: worker produkcyjny kończy brak adaptera AI jako `partial/no_mutation`; pełny adapter pozostaje osobnym krokiem produkcyjnym.
- [x] P1: `partial` nie publikuje `scoped_commit` nowych faktów i zachowuje last-known-good.
- [x] P1: sprzeczne fakty z wielu źródeł są oznaczane jako unresolved/review, a nie rozstrzygane kolejnością.
- [x] P2: cancel po ostatnim Scrape jest sprawdzany przed AI i scoped commit.
- [x] P2: błąd adaptera AI daje kontrolowany `partial` po side effects, nie fałszywy `failed`.
- [x] P2: runtime RLS wykonuje odmowę zapisu użytkownika must-change dla każdej tabeli historii.

### Unit 8.5 — ograniczony re-review `8b766a5..3745c45`

- [ ] P1: nie tworzyć placeholderowego `semantic_benchmark`; scoped refresh nie może zapisać snapshotu grupy bez pełnej projekcji istniejącego scope.
- [ ] P1: timeout musi zatrzymać operację providera, a nie zostawić daemon thread po terminalizacji jobu.
- [ ] P1: dostarczyć fakty kanoniczne dla zakresu Unit 8.5 i użyć OpenAI wyłącznie do braków/niejednoznaczności.
- [ ] P2: każde potwierdzone anulowanie ma zwracać `cancelled`, także przed Search i między Scrape.
- [ ] P2: dodać pełny offline kontrakt job → pipeline → worker → fenced commit dla exact product/configuration/participants.
- [ ] P2: rozszerzyć opt-in RLS o anon/read i rzeczywiste buckety `source-raw`/`source-clean`.

### Unit 8.5 — remediation `3745c45..HEAD` (`2026-08-06`)

- [x] Product-only refresh nie emituje placeholderowego benchmarku grupy.
- [x] FirecrawlClient przyjmuje deadline transportu; refresh przekazuje pozostały timeout bez daemon thread.
- [ ] Pełny canonical fact extraction i ograniczony fallback OpenAI dla nierozstrzygniętych pól.
- [x] Cancellation przed Search i między Scrape kończy się `cancelled`.
- [x] Offline job → pipeline → worker → fenced commit obejmuje exact product/configuration/participants i tylko snapshot produktu.
- [x] Opt-in runtime test obejmuje anon/viewer/must-change/analyst i buckety `source-raw`/`source-clean`.
- [ ] Weryfikacja opt-in lokalnego Supabase oraz końcowy review PASS.

### Unit 8.5 — ograniczony re-review `3745c45..fe4253a`

- [x] P1: exhausted deadline wspólnego FirecrawlClient kończy refresh jako kontrolowany `partial`, nie `failed`; regresja używa rzeczywistego klienta z fixture transportem.
- [x] P1: dodano schema-named canonical facts, evidence/candidates per field oraz ograniczony, wstrzykiwalny fallback AI wyłącznie dla nierozstrzygniętych pól (bez domyślnego płatnego klienta).
- [x] P2: regresja cancel między dwoma Scrape wykonuje branch przed drugim pobraniem.
- [x] P2: scope commit przechodzi przez rzeczywisty output ProductRefreshService → pipeline → worker, bez ręcznie zbudowanego envelope.
- [x] P2: opt-in RLS obejmuje anon/viewer/must-change read oraz analyst write dla każdej tabeli `product_refresh_*`; wykonanie lokalnego runtime pozostaje wymagane.

### Unit 8.5 — remediation `8b766a5..HEAD` (`2026-08-06`)

- [x] Typed job utrwala `configuration`, a pipeline przekazuje ją do refreshu.
- [x] Provider Search/Scrape działa pod deadline; cancel po Scrape kończy się `cancelled` bez publikacji.
- [x] Refresh buduje deterministyczne fakty/evidence oraz ograniczony `scoped_commit` produktu bez płatnego OpenAI.
- [x] Dodano regresje workerowego `partial/no_mutation`, dodatniego `max_pages`, cancel między Scrape i timeoutu.
- [x] Dodano opt-in PostgREST test trzech tabel historii i Storage; wymaga uruchomionego Supabase.
- [ ] Weryfikacja runtime PostgREST/Storage oraz pełny offline gate.
- [ ] Review końcowy PASS.
