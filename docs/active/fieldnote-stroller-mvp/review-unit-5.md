# Review — Unit 5: Kolejka PostgreSQL i worker z dwoma slotami

- **Data:** 2026-07-28
- **Zakres diffu:** `e04145b^..e04145b`
- **Tryb:** pełny review
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, ui_reviewer, data_reviewer`
- **Gate:** `BLOKUJE`

## Kryteria akceptacji unitu

- API zapisuje trwały job i natychmiast zwraca `job_id`, bez subprocessu w request thread.
- Worker atomowo rezerwuje job przez `FOR UPDATE SKIP LOCKED`, lease i heartbeat.
- PostgreSQL wymusza maksymalnie dwa aktywne joby różnych produktów oraz jeden aktywny job produktu.
- Status, eventy i usage są odtwarzalne z PostgreSQL po restarcie API/workera.
- Limity stron, tokenów, timeoutu, retry i kosztu ograniczają wykonanie, a przekroczenie daje `partial` z zachowaniem poprawnych danych.
- Anulowanie jest respektowane między etapami i bezpośrednio przed commitami.
- UI wykonuje enqueue, polling, listowanie, retry i cancel przez trwałe API jobów.

## Zgodność z planem i zakresem

Review objął wyłącznie commit Unit 5 `e04145b`. Nie recenzowano Unit 6 ani
przyrostowego rebuildowania. Implementacja tworzy właściwe warstwy API, worker,
RPC i podstawowe stany UI, lecz krytyczne kontrakty lease, bezpieczeństwa,
selekcji źródeł, limitów kosztu i anulowania nie są spełnione.

## Skonsolidowane findings

### P1 — blocking

#### P1 — Analityk może ominąć FastAPI i przejąć stan kolejki

- **File:** `supabase/migrations/202607280001_durable_research_queue.sql:4`,
  `supabase/migrations/202607230005_auth_roles_rls_storage.sql:71`
- **Evidence:** `authenticated` nadal ma bezpośrednie DML na wszystkich tabelach,
  a polityki `analyst_write` zezwalają na `FOR ALL` dla `research_jobs` i
  `research_job_events`. Nowa migracja nie odbiera tych uprawnień dla pól
  sterowanych przez worker: statusu, lease, tokenu, heartbeat, payloadu, usage
  i eventów.
- **Impact:** użytkownik analyst może ominąć walidację API, sfabrykować leased
  joby, zablokować oba sloty, zmienić historię albo uruchomić nieautoryzowany
  płatny payload.
- **Scenario:** bezpośredni PostgREST `INSERT/UPDATE` tworzy dwa joby `running`
  z dalekim `lease_expires_at`; claim RPC nie przyjmuje prawidłowych jobów.
- **Recommendation:** odebrać `authenticated` bezpośredni zapis do tabel
  kolejki/eventów i usunąć ich `analyst_write`; mutacje pozostawić wyłącznie
  serwerowemu API/service-role, zachowując minimalny odczyt.
- **Missing test:** runtime PostgREST odrzuca DML analysta na jobach/eventach,
  a enqueue/cancel przez FastAPI nadal działa.

#### P1 — Heartbeat workera nigdy się nie uruchamia

- **File:** `fieldnote-api/worker.py:38`
- **Evidence:** event `alive` jest ustawiany przed startem wątku, więc
  `alive.wait(timeout)` natychmiast zwraca `True`, a pętla
  `while ... is False` kończy się bez pierwszego heartbeat.
- **Impact:** po wygaśnięciu lease drugi worker może ponownie uruchomić ten sam
  płatny pipeline. Fencing chroni tylko zapis terminalnego statusu, nie
  duplikowane wywołania i commity legacy.
- **Scenario:** job trwa dłużej niż 60 sekund, a drugi worker wykonuje polling;
  SQL requeue'uje nadal działający job i przydziela go ponownie.
- **Recommendation:** użyć osobnego, początkowo nieustawionego stop-eventu z
  `while not stop.wait(interval)`, obsłużyć błąd heartbeat jako utratę lease
  i zatrzymać/fence'ować drzewo procesów.
- **Missing test:** wykonanie dłuższe niż jeden lease wysyła heartbeat i nie może
  zostać przejęte przez drugiego workera.

#### P1 — Trwała selekcja źródeł nie trafia do pipeline

- **File:** `fieldnote-api/services/pipeline_service.py:33`
- **Evidence:** `selected_offer_ids` jest używane wyłącznie do wyliczenia
  pozornego usage; service nie tworzy ani nie przekazuje `--run-context`.
  `selected_manufacturer_source_ids` i `include_manufacturer_sources` są
  całkowicie ignorowane. CLI przechodzi więc ścieżką wspólnego
  `new_offers.csv`.
- **Impact:** główny flow może przetworzyć niewybrane oferty i pominąć wybrane
  źródła producenta.
- **Scenario:** listing zawiera A i B, użytkownik wybiera tylko A, lecz worker
  uruchamia no-context branch i przetwarza oba rekordy.
- **Recommendation:** utworzyć sekretnie bezpieczny immutable run context z
  payloadu joba i przekazać go do CLI, obejmując także źródła producenta.
- **Missing test:** dodatkowe źródła w cache nie mogą wejść do runu poza dokładną
  selekcją zapisaną w jobie.

#### P1 — Limity kosztu, stron, tokenów i retry nie ograniczają wykonania

- **File:** `fieldnote-api/services/pipeline_service.py:33`,
  `fieldnote-api/worker.py:64`,
  `supabase/migrations/202607280001_durable_research_queue.sql:33`
- **Evidence:** tylko timeout trafia do subprocessu. Liczba stron jest równa
  liczbie zaznaczonych ID, tokeny są zawsze `0`, koszt nie jest zbierany, a
  limity sprawdzane są dopiero po zakończeniu i commitach. `max_retries` jest
  tylko zapisany w payloadzie; wygasłe joby są requeue'owane bez limitu, a
  endpoint retry może tworzyć kolejne joby bez ograniczenia.
- **Impact:** płatne wywołania mogą przekroczyć każdy budżet, job może fałszywie
  raportować `succeeded` i zerowe usage, a awarie mogą powodować nieskończone
  ponowienia.
- **Scenario:** `max_pages=1`, `max_ai_tokens=5`, `max_retries=1`, pipeline
  wykonuje wiele fetchy i tokenów, po czym zapisuje usage `pages=1`,
  `ai_tokens=0`.
- **Recommendation:** egzekwować limity przed każdym płatnym etapem, zbierać
  rzeczywiste usage/attempts, atomowo zatrzymywać job po retry cap i wyprowadzać
  `partial` z trwałych, prawdziwych liczników.
- **Missing test:** metered offline worker→pipeline zatrzymuje kolejne wywołania
  po limitach oraz runtime SQL nie pozwala przekroczyć `max_retries`.

#### P1 — Cancel i timeout nie chronią przed późniejszym commitem

- **File:** `scripts/run_model_research_pipeline.py:205`,
  `fieldnote-api/services/pipeline_service.py:50`
- **Evidence:** cancel jest sprawdzany przed i po całym commit-capable child
  processie. Cancel w trakcie childa zostanie zauważony dopiero po jego zapisie.
  Zewnętrzny timeout używa `subprocess.run` bez kontrolowanego process group,
  więc potomny etap może dalej pisać po terminalnym `partial`.
- **Impact:** anulowany lub timeoutowany job może nadal zmieniać artefakty i
  dane, łamiąc semantykę terminalnego statusu.
- **Scenario:** child zatrzymuje się bezpośrednio przed zapisem; użytkownik
  anuluje job, child zapisuje dane, dopiero potem parent zauważa cancel.
- **Recommendation:** nadzorować całe drzewo procesów, propagować cancel/fencing
  do commit-capable children i sprawdzać autorytatywną flagę bezpośrednio przy
  ich granicy zapisu.
- **Missing test:** deterministyczny mid-stage cancel/timeout nie pozostawia
  żywego procesu ani późniejszego commitu.

### P2 — important

#### P2 — Brak wykonawczego testu transakcji i konkurencji PostgreSQL

- **File:** `tests/test_postgres_job_queue.py:35`,
  `tests/test_worker_leases.py:31`
- **Evidence:** test migracji sprawdza wyłącznie tekst SQL, a fake queue używa
  sekwencyjnego `list.pop()`. Nie wykonuje advisory lock, `SKIP LOCKED`,
  limitu dwóch slotów, odzyskania lease ani stale-token fencing.
- **Impact:** centralny kontrakt kolejki może być składniowo lub transakcyjnie
  błędny mimo zielonej bramki.
- **Scenario:** trzy równoległe claimy przechodzą w lokalnym PostgreSQL, ale fake
  nadal daje dwa kolejne elementy i test jest zielony.
- **Recommendation:** dodać opt-in lokalny runtime contract z równoległymi
  połączeniami i trzema produktami.
- **Missing test:** dokładnie dwa z trzech jobów są aktywne, jeden job ma jednego
  claimera, wygasły lease jest przejmowany, stary token nie finalizuje.

#### P2 — Wygasły anulowany job blokuje produkt bez końca

- **File:** `supabase/migrations/202607280001_durable_research_queue.sql:33`
- **Evidence:** recovery ustawia każdy wygasły leased/running job na `queued`,
  lecz claim wybiera wyłącznie `cancel_requested_at is null`.
- **Impact:** job pozostaje aktywny w częściowym unique indexie i blokuje nowy
  research produktu.
- **Scenario:** użytkownik anuluje running job, worker umiera, lease wygasa;
  kolejny claim requeue'uje job, ale nigdy go nie pobiera ani nie terminalizuje.
- **Recommendation:** wygasłe anulowane joby terminalizować jako `cancelled`
  z `completed_at` i eventem; requeue'ować tylko nieanulowane.
- **Missing test:** expired cancelled job zwalnia indeks produktu i pozwala
  utworzyć następny job.

#### P2 — API odpytuje eventy niewłaściwym identyfikatorem

- **File:** `fieldnote-api/repositories/job_repository.py:52`
- **Evidence:** `research_job_events.job_id` wskazuje wewnętrzny UUID
  `research_jobs.id`, lecz repository filtruje go publicznym tekstowym
  `research_jobs.job_id`.
- **Impact:** detail joba zwraca pustą historię mimo zapisanych leased/running/
  terminal events, więc status nie jest w pełni odtwarzalny przez API.
- **Scenario:** wewnętrzny `id` i publiczny `job_id` są różne; GET detail nie
  znajduje żadnego eventu.
- **Recommendation:** rozwiązać wewnętrzny ID przed query albo dodać join/RPC
  przyjmujący publiczny `job_id`.
- **Missing test:** distinct internal/public ID daje pełną historię eventów.

#### P2 — Lista jobów raportuje fałszywy total i ucina historię

- **File:** `fieldnote-api/routers/jobs.py:75`,
  `fieldnote-frontend/src/app/App.tsx:2091`
- **Evidence:** router zwraca `total=len(runs)` już po limit/offset, a UI pobiera
  tylko pierwsze 50 rekordów i nie ma paginacji.
- **Impact:** po 51. jobie starsza historia znika, a nagłówek nadal pokazuje
  `50 uruchomień łącznie`.
- **Scenario:** 75 jobów, request `limit=50` zwraca `total=50`.
- **Recommendation:** pobierać niezależny count z bazy i dodać paginację lub
  load-more w UI.
- **Missing test:** więcej rekordów niż limit daje `total > runs.length` i
  dostęp do następnej strony.

#### P2 — Polling historii usuwa aktywne kontrolki i może cofać stan

- **File:** `fieldnote-frontend/src/app/App.tsx:2091`
- **Evidence:** każdy background poll wywołuje `loadRuns()`, które ustawia
  `loading=true`; timeline jest zastępowany komunikatem ładowania. Powolne,
  nakładające się requesty nie są anulowane ani serializowane.
- **Impact:** lista, cancel i log migają co dwie sekundy, a starsza odpowiedź
  może nadpisać nowszy status.
- **Scenario:** drugi request jest wolny podczas aktywnego joba; wiersz i cancel
  znikają, a odpowiedzi wracają w odwrotnej kolejności.
- **Recommendation:** rozdzielić initial loading od background refresh,
  zachować stale rows i anulować/ignorować superseded requests.
- **Missing test:** aktywny wiersz oraz cancel pozostają widoczne podczas
  odroczonego pollingu, a stara odpowiedź nie nadpisuje nowej.

#### P2 — Durable DTO pomija dane potrzebne do diagnozy i retry

- **File:** `fieldnote-api/routers/jobs.py:40`,
  `fieldnote-frontend/src/app/App.tsx:2033`
- **Evidence:** `public_job()` nie wystawia m.in. `error`, `retry_of`,
  `sources_selected`, `coverage_before` ani `coverage_after`, choć UI te pola
  renderuje.
- **Impact:** failed job nie pokazuje przyczyny, historia raportuje zero źródeł
  i puste coverage, a operator nie widzi lineage retry.
- **Scenario:** worker kończy się błędem lub powstaje retry; UI pokazuje
  terminalny stan bez strukturalnego wyjaśnienia i z mylącymi licznikami.
- **Recommendation:** zdefiniować jawny DTO joba i mapować result/usage/lineage
  do pól używanych przez UI.
- **Missing test:** failed, partial i retried response pokazują poprawny błąd,
  liczniki, coverage i retry provenance.

### P3 — non-blocking

Brak.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | findings | 6 | 0 |
| security_reviewer | findings | 2 | 0 |
| test_reviewer | findings | 5 | 0 |
| ui_reviewer | findings | 3 | 0 |
| data_reviewer | findings | 5 | 0 |

Powtarzające się uwagi o limitach, RLS, recovery, eventach i paginacji zostały
scalone do pojedynczych findings powyżej.

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused backend | PASS | `python -m unittest tests/test_postgres_job_queue.py tests/test_worker_leases.py tests/test_job_cost_limits.py tests/test_fieldnote_api_contracts.py` — 32 testy |
| Frontend tests | PASS | `pnpm test` — 17 testów |
| Frontend typecheck | PASS | `pnpm run typecheck` |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` |
| Spójność diffu | PASS | `git diff --check e04145b^ e04145b` |
| Runtime PostgreSQL concurrency/RLS | BRAK | wymagany przez zaakceptowane P1/P2; obecne testy nie wykonują RPC ani PostgREST queue DML |

## Bezpieczeństwo

Service-role RPC nie wystarcza jako granica, ponieważ odziedziczone granty i RLS
pozwalają analystowi bezpośrednio modyfikować obie tabele kolejki. Do czasu
odebrania tego DML joby, lease, usage i eventy nie są zaufanym durable state.
Nie znaleziono nowych sekretów w diffie.

## Odchylenia od planu

- `fieldnote-api/run_coordinator.py` nie został zmodyfikowany; pozostawienie go
  jako legacy-only nie jest samo w sobie findingiem.
- Faktyczne usage providerów będzie pogłębiane przy wspólnych adapterach Unit 7,
  ale Unit 5 już teraz musi egzekwować własne jawne limity i nie może raportować
  zmyślonych liczników.
- Przyrostowy rebuild pozostaje prawidłowo poza zakresem, w Unit 6.

## Kontrole operatora

Nie wykonano płatnych Firecrawl/OpenAI ani publicznego wdrożenia. Nie oznaczono
runtime PostgreSQL concurrency/RLS jako PASS, ponieważ repo nie zawiera
wykonawczego testu tych kontraktów.

## Decyzja gate

**BLOKUJE** — 5 P1, 6 P2, 0 P3. Unit 5 nie ma PASS i Unit 6 nie może zostać
rozpoczęty.

## Rekomendowany następny krok

Uruchomić `$dev-docs-execute docs/active/fieldnote-stroller-mvp 5` i naprawić
wyłącznie zaakceptowane P1/P2 z tego raportu. Po poprawkach wykonać ograniczony
re-review Unit 5.

## Stan po wykonaniu napraw (execute Unit 5)

Wdrożono poprawki wskazane powyżej: kolejka ma service-role-only DML, worker
odnawia lease i stosuje fencing, run context przenosi selekcję ofert/źródeł,
limity i cancel są egzekwowane, a UI/API obsługują trwały total, paginację,
stany terminalne i metadane diagnostyczne. Zmieniono wyłącznie zakres Unit 5.

Weryfikacja: focused backend 32 PASS, frontend 20 PASS, typecheck/build PASS,
`bash scripts/check_fieldnote.sh` PASS oraz `git diff --check` PASS.
Ten dokument pozostaje raportem pierwotnego review; wynik PASS wymaga jeszcze
ograniczonego re-review tych poprawek. Unit 6 nie rozpoczęto.

## Ograniczony re-review — lokalny PostgreSQL concurrency/RLS

- **Data:** 2026-07-28
- **Zakres diffu:** `e04145b..8c50b59`, ograniczony wyłącznie do poprzedniego
  P2 „wykonawczy lokalny test PostgreSQL concurrency/RLS”.
- **Tryb:** re-review
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, data_reviewer`
- **Gate:** `WYMAGA POPRAWEK`

### Skonsolidowane findings

#### P2 — Brakuje wykonawczego lokalnego kontraktu kolejki PostgreSQL/RLS

- **File:** `tests/test_postgres_job_queue.py:35`,
  `tests/test_worker_leases.py:31`, `tests/test_supabase_runtime_contract.py:259`
- **Evidence:** commit `8c50b59` nie zmienia żadnego testu kolejki. Pierwsze dwa
  pliki używają odpowiednio inspekcji tekstu migracji i kolejki in-memory;
  opt-in suite lokalnego Supabase nie wywołuje `research_jobs`,
  `research_job_events` ani RPC `fieldnote_*research_job`.
- **Impact:** błąd transakcji/RLS może dopuścić trzeci lease, podwójny claim,
  zapis starym tokenem albo bezpośredni DML analysta mimo zielonej bramki offline.
- **Scenario:** trzy współbieżne claimy lokalnego PostgreSQL mogą objąć trzy
  joby albo stary token może sfinalizować odzyskany job; obecne fakes pozostaną
  zielone.
- **Recommendation:** dodać opt-in test dla `supabase start` z niezależnymi
  połączeniami/RPC i PostgREST JWT. Nie umieszczać kluczy w repozytorium.
- **Missing test:** trzy różne joby dają dokładnie dwa lease, współbieżny claim
  jednego joba ma jednego zwycięzcę, wygasły lease jest odzyskiwany, stary token
  nie heartbeatuje ani nie finalizuje po odzyskaniu, a anon/analyst nie wykonują
  DML jobs/events przy działającym service-role RPC.

### Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | P2 | 1 | 0 |
| security_reviewer | P2 | 1 | 0 |
| test_reviewer | P2 | 1 | 0 |
| data_reviewer | P2 | 1 | 0 |

Uwagi są tym samym findingiem i zostały scalone.

### Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused queue/worker + runtime suite | PASS z pominięciem runtime | 13 testów, w tym 5 `skip` bez `FIELDNOTE_SUPABASE_INTEGRATION=1` |
| Spójność diffu | PASS | `git diff --check 8c50b59^..8c50b59` |
| Lokalny runtime PostgreSQL | NIE WYKONANO | `supabase status --output env` nie uruchomił się w sandboxie przez próbę zapisu telemetry do `~/.supabase`; niezależnie repo nie zawiera testu kolejki do uruchomienia |

### Decyzja gate

**WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3. Unit 5 nie ma PASS i Unit 6 nie może
zostać rozpoczęty.

### Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 5` — dodać wyłącznie
wykonawczy opt-in lokalny test PostgreSQL concurrency/RLS opisany w P2, następnie
uruchomić ograniczony `$dev-docs-review docs/active/fieldnote-stroller-mvp 5`.

## Stan po wykonaniu P2 (execute Unit 5)

Dodano `tests/test_supabase_runtime_contract.py::test_durable_queue_rpc_concurrency_fencing_and_rls`.
Test korzysta z aktualnego lokalnego Supabase i obejmuje równoległe claimy,
limit dwóch slotów, jednego zwycięzcę wyścigu, recovery/fencing, terminalizację
wygasłego anulowanego joba oraz odmowę INSERT/PATCH/DELETE anon i analyst na
`research_jobs` i `research_job_events`.

Weryfikacja: opt-in runtime suite 6 PASS, focused backend 32 PASS,
`git diff --check` PASS, offline gate uruchomiony. Wynik PASS Unit 5 wymaga
jeszcze ograniczonego re-review tej poprawki. Unit 6 nie rozpoczęto.
