# Review — Unit 6: Przyrostowe commitowanie i przeliczanie

- **Data:** 2026-07-29
- **Zakres diffu:** `b59d169..1e37e3e`
- **Tryb:** `pełny review`; `data_reviewer` jako `single-agent fallback`
- **Reviewers:** `correctness_reviewer`, `security_reviewer`, `test_reviewer`, data single-agent fallback
- **Gate:** `BLOKUJE`

## Kryteria akceptacji unitu

- Research jednego produktu zmienia wyłącznie produkt, jego źródła/evidence,
  powiązane benchmarki konkurencyjne i jedną grupę wewnętrzną.
- Normalny research nie wykonuje globalnego przebudowania katalogu ani eksportu
  statycznego frontendu.
- Pełny rebuild jest osobną, serializowaną akcją administracyjną i nie ściga
  się z normalnym commitem.
- Run zapisuje się zawsze, a snapshot tylko przy istotnej zmianie; próg ceny
  wynosi 5%.
- Suma rebuildów przyrostowych daje ten sam stan co admin full rebuild na
  fixture.

## Zgodność z planem i zakresem

Zakres `b59d169..1e37e3e` tworzy service i CLI dla fixture JSON, dodaje
`--group-key` do benchmarku/coverage oraz przekazuje scope z durable worker
contextu. Nie uruchamiano Unit 7 i nie zmieniano UI.

Nie spełnia jednak pełnego kontraktu Unit 6 w kanonicznym runtime: bez
immutable contextu normalne polecenie CLI dalej uruchamia globalne etapy 8–9,
runtime worker nie utrwala transitionu snapshotu przez repozytoria Supabase,
a locki nie obejmują wspólnego read–modify–write artefaktów.

## Skonsolidowane findings

### P1 — Kanoniczny CLI nadal wykonuje globalny rebuild

- **File:** `scripts/run_model_research_pipeline.py:717,1037-1045`
- **Evidence:** `--group-key` jest dodawany tylko, gdy `--run-context` zawiera
  `product_scope`. Udokumentowane polecenie README uruchamia jeden produkt bez
  tego contextu, więc etapy 8–9 wywołują buildery bez scope i skanują cały
  katalog.
- **Impact:** zwykły research produktu zmienia niepowiązane benchmarki i
  coverage, wprost łamiąc główny cel Unit 6.
- **Scenario:** uruchomić README `--apply --resume` dla ORFEO bez
  `--run-context`; benchmark i coverage zostaną przebudowane dla wszystkich
  grup.
- **Recommendation:** twórz i egzekwuj scope dla każdego researchu jednego
  produktu; unscoped rebuild zostaw wyłącznie dla jawnej ścieżki admin full
  rebuild.
- **Missing test:** offline test kanonicznego CLI bez contextu, który potwierdza
  zachowanie hashy niepowiązanych grup i brak globalnego eksportu.

### P1 — Scoped commit i admin full rebuild mogą utracić aktualizację

- **File:** `scripts/run_model_research_pipeline.py:226-230`,
  `scripts/build_model_benchmark.py:93-108`,
  `scripts/report_model_coverage.py:82-91`,
  `fieldnote-api/services/benchmark_rebuild_service.py:186-211`
- **Evidence:** scoped runner blokuje po `run_id`, więc dwa produkty używają
  różnych locków, a oba procesy mogą odczytać ten sam CSV i później atomowo
  zapisać własny merge. Admin lock nie jest sprawdzany w scoped runnerze;
  service używa jedynie podatnego na wyścig `exists()` przed product lockiem,
  zaś zapis JSON następuje po zwolnieniu locka.
- **Impact:** dwa legalne joby mogą zakończyć się sukcesem, a ostatni zapis
  usuwa wynik pierwszego; admin full rebuild może pozostawić niespójny stan.
- **Scenario:** równolegle uruchomić scoped rebuild produktów A i B: oba czytają
  stary benchmark, A zapisuje `old+A`, B zapisuje `old+B`, przez co A znika.
- **Recommendation:** zastosować wspólny trwały lock/transakcję/advisory lock
  obejmującą cały read–merge–commit oraz jednolity protokół współpracy z admin
  full rebuild.
- **Missing test:** barrier-controlled test dwóch scope'ów i nakładającego się
  admin rebuild, wymagający zachowania obu aktualizacji albo bezpiecznego retry.

### P1 — Snapshoty semantyczne pozostają wyłącznie fixtureem JSON

- **File:** `fieldnote-api/services/benchmark_rebuild_service.py:127-211`,
  `fieldnote-api/services/pipeline_service.py:94-120`,
  `fieldnote-api/worker.py:52-56`
- **Evidence:** service transformuje tylko przekazany mapping i jest wywoływany
  wyłącznie przez nowe CLI `--input/--output`; durable worker uruchamia legacy
  runner przez `PipelineService` i finalizuje job bez wywołania service ani
  zapisu `benchmark_snapshots` przez repozytorium Supabase.
- **Impact:** produkcyjny job z istotną zmianą może dostać `succeeded`, ale nie
  zostawić wymaganego trwałego snapshotu/provenance ani `snapshot_updated`.
- **Scenario:** worker przetwarza produkt z ceną zmienioną o 5%; legacy etapy
  kończą się powodzeniem, lecz nie ma transitionu snapshotu w bazie.
- **Recommendation:** wywołuj scoped rebuild i zapis snapshotu przez
  repozytoria Supabase we fenced completion path workera; sukces joba zwracaj
  dopiero po trwałym commicie.
- **Missing test:** worker/repository integration dla 4,99% i 5%, w tym błąd
  persistence blokujący `succeeded`.

### P2 — Scoped benchmark pozostawia stare wiersze po utracie eligibility

- **File:** `scripts/build_model_benchmark.py:63-105`
- **Evidence:** gdy wskazana grupa nie przejdzie `is_benchmark_eligible`, nie
  powstaje update row. Merge usuwa stare rekordy wyłącznie dla kluczy obecnych
  w `updates`, a nie dla wszystkich żądanych `scoped_keys`.
- **Impact:** nieaktualny benchmark i evidence mogą pozostać widoczne dla
  produktu, który nie jest już kwalifikowany.
- **Scenario:** uprzednio eligible group zmienia taxonomy na
  `review_required`, potem przechodzi `--group-key`; wcześniejszy wiersz CSV
  pozostaje.
- **Recommendation:** usuń rekordy benchmark/source dla wszystkich żądanych
  scope'ów przed dołączeniem aktualnie eligible rows oraz zaktualizuj quality.
- **Missing test:** fixture z istniejącym eligible row, następnie zmiana na
  ineligible i asercja usunięcia obu CSV rows.

### P2 — Testy nie rozróżniają izolacji grupy wewnętrznej

- **File:** `tests/test_incremental_pipeline.py:15-52`,
  `tests/test_incremental_benchmark_rebuild.py:15-73`
- **Evidence:** oba fixture zawierają tylko `benchmark_group="compact"`.
  Testy nie uruchamiają też changed pipeline/builders, więc nie wykryją
  usunięcia przekazywania `--group-key` ani mutacji wszystkich grup.
- **Impact:** regresja rozszerzająca rebuild na wszystkie grupy może przejść
  offline gate mimo niespełnienia kryterium Unit 6.
- **Scenario:** implementacja przebudowuje każdą grupę wewnętrzną; obecne
  fixture nadal przechodzą, bo nie mają niepowiązanej grupy do porównania.
- **Recommendation:** dodać fixture z co najmniej dwiema grupami i test
  kanonicznego pipeline'u; asercje mają obejmować komendy `--group-key`, hashe
  niepowiązanych artefaktów oraz brak eksportu frontendu.
- **Missing test:** offline integration test z dwoma grupami i mockowanymi
  child commands.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | findings | 4 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | findings | 2 (1 zduplikowany z correctness) | 0 |
| data_reviewer | single-agent fallback | 1 zduplikowany z correctness | 0 |

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused Unit 6 | PASS | `fieldnote-api/.venv/bin/python -m unittest tests/test_incremental_pipeline.py tests/test_incremental_benchmark_rebuild.py` — 7 testów |
| Spójność diffu | PASS | `git diff --check b59d169..1e37e3e` |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` (backend, checkery, frontend typecheck/test/build) |
| Test współbieżności scoped/admin | brak | obecny test sprawdza wyłącznie wcześniej istniejący plik locka |
| Worker → durable snapshot | brak | brak integracji i testu repozytorium |

## Bezpieczeństwo

`security_reviewer`: PASS. W diffie nie znaleziono nowego bypassu auth/RLS,
sekretu, zdalnie osiągalnej akcji admina ani obsługi zewnętrznej treści
naruszającej granicę bezpieczeństwa.

## Odchylenia od planu

Plan wymaga produkcyjnego scoped commitowania i serializowanego admin rebuild.
Obecny service/CLI JSON jest użytecznym fixture adapterem, lecz nie jest
podłączony do durable workera ani Supabase source of truth.

## Kontrole operatora

Brak ręcznych kontroli do oznaczenia jako wykonane.

## Decyzja gate

**BLOKUJE** — 3 P1, 2 P2, 0 P3. Unit 6 nie jest ukończony; Unit 7 pozostaje
poza zakresem.

## Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 6` — napraw wyłącznie
zaakceptowane P1/P2 z tego raportu; nie rozpoczynaj Unit 7.

## Remediacja oczekująca na re-review

- **Zakres proponowanego re-review:** `1e37e3e..HEAD` (po commicie użyć
  dokładnego SHA); bez Unit 7.
- Normalny runner zawsze przekazuje scope i `--group-key`; globalny export nie
  jest ścieżką zwykłego researchu. Fixture CLIs serializują pełny
  read–merge–write wspólnym lockiem, a SQL RPC serializuje trwały worker
  advisory lockiem oraz fencingiem lease.
- `research_scope_snapshots` i `fieldnote_commit_incremental_research_job`
  zapewniają atomową terminalizację joba wraz z semantycznym snapshotem;
  błąd persistence blokuje powodzenie workera.
- Dodano regresje stale-row, dwóch grup, canonical command, ceny oraz
  równoległych scope'ów/admina. Wstępne testy: 27 PASS, `py_compile` PASS,
  pełny `bash scripts/check_fieldnote.sh` PASS, `git diff --check` PASS;
  lokalne `supabase migration up --local` potwierdziło nową tabelę i RPC.
- Status pozostaje **WYMAGA RE-REVIEW**; nie oznaczono PASS ani nie rozpoczęto
  Unit 7.

## Ograniczony re-review remediacji Unit 6

- **Data:** 2026-07-29
- **Zakres diffu:** `002c371^..002c371` (`1e37e3e..002c371`)
- **Tryb:** `ograniczony re-review` wyłącznie pięciu wcześniejszych findings
  P1/P2 oraz ich regresji
- **Reviewers:** `correctness_reviewer`, `security_reviewer`,
  `test_reviewer`, `data_reviewer`
- **Gate:** `BLOKUJE`

### Kryteria akceptacji i zakres

Sprawdzono wyłącznie scoped normal CLI, serializację scoped/admin,
worker → fenced Supabase snapshot, usuwanie stale rows oraz testy dwóch grup.
Nie sprawdzano Unit 7 ani nie zmieniano kodu podczas review.

### Skonsolidowane findings

#### P1 — Cena jest usuwana przed wyliczeniem mediany durable snapshotu

- **File:** `scripts/run_model_research_pipeline.py:122-136`,
  `scoped_commit_payload`
- **Evidence:** `group_data["sources"]` zachowuje wyłącznie identyfikatory,
  po czym `source_price_median(group_data)` czyta pola ceny, których projekcja
  już nie zawiera. Emitted `scoped_commit.price_median` jest więc `null`.
- **Impact:** cena zmieniona o co najmniej 5% nie tworzy durable snapshotu,
  mimo że to materialna zmiana wymagana przez Unit 6.
- **Scenario:** źródła produktu przechodzą z mediany 1000 do 1050, bez zmiany
  evidence ani pozostałych pól; RPC nie otrzymuje ceny i nie zapisuje zmiany.
- **Recommendation:** wyliczyć medianę z oryginalnych records źródeł przed
  projekcją identifier-only i przekazać ją w semantic envelope.
- **Missing test:** fixture `scoped_commit_payload` z cenami 100 → 104,99 oraz
  100 → 105, wraz z asercją decyzji snapshotu.

#### P1 — Brak scoped envelope zmienia prawidłowy wynik `partial` w `failed`

- **File:** `fieldnote-api/worker.py:58-63`,
  `fieldnote-api/services/benchmark_commit_service.py:29-30`
- **Evidence:** worker przekazuje każdy `partial` do committera; preflight
  limitu stron i timeout PipelineService zwracają `partial` bez
  `scoped_commit`, co wywołuje wyjątek i późniejsze legacy `complete(...,
  "failed", ...)`.
- **Impact:** limit kosztu/timeout traci semantykę `partial`, historię i
  zachowanie operatora przewidziane dla bounded researchu.
- **Scenario:** 11 wybranych ofert przy `max_pages=10` kończy się jako
  `failed`, zamiast trwałego `partial` bez snapshotu.
- **Recommendation:** terminalizować no-mutation `partial` przez fenced path
  zachowujący `partial`; RPC snapshotu stosować tylko po istniejącym scoped
  semantic commicie.
- **Missing test:** worker integration dla preflight page limit i timeout,
  asertująca `partial` i brak snapshotu.

#### P2 — Direct normal CLI nie ma wykonawczego testu izolacji scope'u

- **File:** `tests/test_incremental_pipeline.py:56-60`
- **Evidence:** test sprawdza helper `derived_stage_commands()`, ale nie
  uruchamia `main()` bez `--run-context`; późniejszy bypass helpera w realnym
  runnerze pozostałby niewykryty.
- **Impact:** regresja przywracająca globalne etapy 8–9 może przejść offline
  gate mimo kryterium głównego flow.
- **Scenario:** main wywołuje nie-scoped builders, pozostawiając helper bez
  zmian.
- **Recommendation:** mockowany CLI integration test bez contextu, który
  przechwytuje komendy etapów 8–9 i wymaga `--group-key` oraz braku eksportu.
- **Missing test:** opisany test canonical direct CLI.

#### P2 — Test nie nakłada adminowego rebuilda na scoped read–merge–write

- **File:** `tests/test_incremental_benchmark_rebuild.py:78-101`
- **Evidence:** test czeka `join()` obu scoped threadów, a dopiero potem
  wywołuje admin full rebuild; nie weryfikuje rzeczywistej kolizji obu klas
  transakcji.
- **Impact:** zmiana lock protocolu może dopuścić lost update w scenariuszu
  admin/scoped bez regresji testowej.
- **Scenario:** admin odczytuje stan przed scoped commitem i nadpisuje jego
  wynik po zwolnieniu locka.
- **Recommendation:** barrier-controlled test z nakładającymi się operacjami
  scoped i admin oraz asercją retry/pełnego końcowego stanu.
- **Missing test:** opisany deterministyczny concurrency test.

#### P2 — Fenced RPC snapshotów nie ma wykonawczego kontraktu PostgreSQL

- **File:** `tests/test_supabase_schema_contract.py:69-77`,
  `tests/test_incremental_benchmark_rebuild.py:103-127`
- **Evidence:** kontrakt SQL jest string inspection, a worker używa fake
  `complete_incremental`; żaden test nie wykonuje RPC dla stale lease,
  atomowego job+snapshot ani błędnego envelope.
- **Impact:** zmiana semantyki migracji może raportować sukces bez trwałego
  snapshotu, mimo zielonych testów fixture.
- **Scenario:** stale token lub invalid snapshot nie jest odrzucony atomowo w
  rzeczywistym PostgreSQL.
- **Recommendation:** opt-in local Supabase runtime test dla 4,99%/5%, stale
  tokenu oraz invalid envelope z asercją braku częściowego zapisu.
- **Missing test:** opisany runtime contract.

#### P2 — Usunięcie stale benchmark/source rows jest testowane tylko helperem

- **File:** `tests/test_incremental_pipeline.py:68-71`
- **Evidence:** test wywołuje `merge_scoped_rows` bez uruchomienia builderów;
  nie pokrywa istniejących benchmark-source CSV ani kwalifikacji grupy.
- **Impact:** CLI builder może nadal pozostawić widoczne stale rows po zmianie
  eligibility.
- **Scenario:** istniejące benchmark, benchmark-source i coverage dla grupy
  zmienionej na ineligible nie są usuwane przez rzeczywiste skrypty.
- **Recommendation:** temporary-output CLI fixture uruchamiający oba buildery
  i zachowujący niepowiązaną grupę byte-for-byte.
- **Missing test:** opisany integration test builderów.

### Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | findings | 2 P1 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | findings | 4 P2 | 3 severity downgraded from P1, because direct code inspection confirms current behavior |
| data_reviewer | finding | 1 P1 (duplikat correctness) | 0 |

### Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused Unit 6 + queue/schema/RLS | PASS | 27 testów |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` |
| Spójność diffu | PASS | `git diff --check 002c371^ 002c371` |
| Lokalna migracja (wykonawca) | PASS | `supabase migration up --local` i bezpieczne query tabeli/RPC |

### Bezpieczeństwo

`security_reviewer`: PASS. Migration ogranicza RPC do `service_role`, RLS
snapshotów używa istniejącego read guard i review nie wykrył nowego sekreta,
bypassu RLS ani niewłaściwego grantu.

### Odchylenia od planu

Brak zmian zakresu funkcjonalnego, ale dwa kryteria Unit 6 pozostają złamane:
5% price snapshot i trwały status `partial`. Unit 7 pozostaje poza zakresem.

### Kontrole operatora

Brak ręcznych kontroli do oznaczenia jako wykonane.

### Decyzja gate

**BLOKUJE** — 2 P1, 4 P2, 0 P3. Unit 6 nie jest ukończony.

### Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 6` — napraw wyłącznie
zaakceptowane 2 P1 i 4 P2 z tego ograniczonego re-review; nie rozpoczynaj
Unit 7.

## Wykonanie remediacji po ograniczonym re-review

- Zakres: wyłącznie zaakceptowane 2 P1 i 4 P2 z review `002c371^..002c371`;
  Unit 7 nie rozpoczęto.
- `scoped_commit_payload()` zachowuje medianę ceny z raw source records,
  a no-mutation `partial` używa fenced incremental RPC bez snapshotów.
- Dodano test direct CLI bez contextu, rzeczywisty overlap scoped/admin,
  builder integration stale-row oraz opt-in runtime RPC dla 4,99%/5%, stale
  lease i invalid envelope. SQL RPC dostał alias dla elementu JSON, aby uniknąć
  niejednoznaczności PL/pgSQL.
- Weryfikacja: focused Unit 6/schema/RLS 28 PASS, opt-in RPC PASS,
  `py_compile` PASS, pełny `bash scripts/check_fieldnote.sh` PASS i
  `git diff --check` PASS.
- Status: **WYMAGA OGRANICZONEGO RE-REVIEW** `002c371^..HEAD`; nie oznaczono
  jeszcze Unit 6 jako ukończonego.

## Ograniczony re-review remediacji `c35f1d7`

- **Data:** 2026-07-30
- **Zakres diffu:** `c35f1d7^..c35f1d7` (`002c371..c35f1d7`)
- **Tryb:** `ograniczony re-review` wyłącznie sześciu wcześniej zaakceptowanych
  findings P1/P2 i ich testów regresyjnych
- **Reviewers:** `correctness_reviewer`, `security_reviewer`,
  `test_reviewer`, `data_reviewer`
- **Gate:** `BLOKUJE`

### Kryteria akceptacji i zakres

Sprawdzono wyłącznie poprawki mediany ceny, no-mutation `partial`, direct CLI,
serializacji scoped/admin, wykonawczego RPC i stale rows. Unit 7 oraz UI są
poza zakresem. Weryfikacja obejmuje również bezpośredni wpływ tych poprawek na
snapshoty i rollout migracji.

### Skonsolidowane findings

#### P1 — Zmiana ceny poniżej 5% nadal tworzy snapshot grupy benchmarkowej

- **File:** `fieldnote-api/services/benchmark_commit_service.py:94-103`,
  `BenchmarkCommitService._snapshots`; `supabase/migrations/202607290001_incremental_benchmark_commit.sql:105-113`
- **Evidence:** standardowy `semantic_state` runnera zawiera `price_median`,
  ale nie `internal_benchmark`. Snapshot grupy używa więc fallbacku całego
  state i hashuje cenę jako `domain_hash`. Sprawdzenie payloadów dla 100 i
  104,99 potwierdza różne hashe grupy, choć hash domeny produktu pozostaje
  bez ceny.
- **Impact:** ruch ceny 4,99% tworzy `benchmark_group` snapshot i zwraca
  `snapshot_updated=true`, łamiąc próg 5% i zasadę snapshotu tylko dla zmiany
  istotnej.
- **Scenario:** dwa identyczne research runy produktu w `compact`, różniące
  się wyłącznie medianą 100 → 104,99.
- **Recommendation:** buduj payload grupy z rzeczywistej agregacji internal
  benchmarku bez ceny pojedynczego produktu; nie emituj snapshotu grupy, gdy
  taka agregacja nie istnieje.
- **Missing test:** dwa kompletne envelope'y runnera 100 → 104,99 przez RPC
  nie tworzą snapshotu produktu ani grupy; istotna zmiana agregatu tworzy jeden
  snapshot grupy.

#### P1 — Poprawka RPC nie wdroży się na bazie z wcześniejszym Unit 6

- **File:** `supabase/migrations/202607290001_incremental_benchmark_commit.sql`
- **Evidence:** commit zmienia treść już wersjonowanej migracji `202607290001`
  (w tym alias elementu JSON i obsługę no-mutation `partial`), lecz nie dodaje
  nowszej migracji zastępującej funkcję. Supabase pomija wersję obecną już w
  historii migracji; `supabase db reset` potwierdza tylko świeżą bazę.
- **Impact:** środowisko, które wdrożyło `002c371`, zachowuje wadliwe RPC,
  podczas gdy worker oczekuje nowej semantyki. Trwały commit może nadal kończyć
  się błędem zamiast utrwalić job/snapshot.
- **Scenario:** staging ma zastosowaną wersję `202607290001`; po zwykłym
  deployu `c35f1d7` funkcja nie jest ponownie wykonana.
- **Recommendation:** zachowaj historyczną migrację bez zmian i dodaj nową,
  sekwencyjną migrację `CREATE OR REPLACE FUNCTION` z poprawionym ciałem.
- **Missing test:** upgrade lokalnej bazy od poprzedniej historii bez resetu,
  zastosowanie wyłącznie migracji następczej i wykonanie prawidłowego RPC oraz
  no-mutation `partial`.

#### P2 — Test serializacji scoped/admin nie dowodzi rzeczywistego overlapu

- **File:** `tests/test_incremental_benchmark_rebuild.py:83-112`
- **Evidence:** bariera jednocześnie zwalnia trzy wątki, ale nie ma hooka,
  który zatrzymałby scoped read–merge–write po wejściu do sekcji krytycznej i
  potwierdził próbę wejścia admina. Przy szczęśliwym szeregowaniu wynik może
  przejść także bez realnej kolizji.
- **Impact:** regresja protokołu locka może nie zostać wykryta mimo deklaracji
  wykonawczego testu współbieżności.
- **Scenario:** scheduler uruchamia każdy rebuild kolejno; test nadal widzi
  oczekiwane ceny i runy.
- **Recommendation:** dodaj wstrzykiwalny hook/barierę po zdobyciu locka;
  rozpocznij admina podczas zatrzymanego scoped commitu i potwierdź, że jego
  zapis następuje dopiero po zwolnieniu locka.
- **Missing test:** deterministyczny fixture concurrency test opisany powyżej.

### Findings odrzucone

- Test reviewer zasugerował P2, bo case invalid envelope nie odczytuje licznika
  snapshotów po błędzie. Odrzucono: w aktualnym SQL wyjątek nie jest łapany,
  więc PostgreSQL wycofuje całą instrukcję RPC; nie ma widocznej ścieżki
  częściowego zapisu. To nie jest obecnie odtwarzalna regresja.

### Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | findings | 2 P1 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | findings | 1 P2 | 1 P2 (spekulacyjne) |
| data_reviewer | findings | 2 P1 (duplikaty correctness) | 0 |

### Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused Unit 6 + schema/RLS | PASS | `fieldnote-api/.venv/bin/python -m unittest tests/test_incremental_pipeline.py tests/test_incremental_benchmark_rebuild.py tests/test_supabase_schema_contract.py tests/test_rls_policy_contract.py` — 28 testów |
| Opt-in fenced RPC | PASS | `FIELDNOTE_SUPABASE_INTEGRATION=1 fieldnote-api/.venv/bin/python -m unittest tests.test_supabase_runtime_contract.SupabaseRuntimeContractTests.test_incremental_commit_rpc_fences_price_threshold_and_partial_without_snapshot -v` — 1 test |
| Python compile | PASS | `fieldnote-api/.venv/bin/python -m py_compile` dla zmienionych modułów i testów |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` |
| Spójność diffu | PASS | `git diff --check c35f1d7^ c35f1d7` |

### Bezpieczeństwo

`security_reviewer`: PASS. Nie wykryto nowego bypassu RLS, rozszerzenia grantów
RPC poza `service_role`, wycieku sekretu ani niezaufanego wejścia, które
przekracza granicę uprawnień. Problem migracji jest przyjęty jako P1 trwałości
i wdrożenia danych, nie jako nowa luka uprawnień.

### Odchylenia od planu

Dwa warunki Unit 6 pozostają niespełnione: durable historia może zmieniać się
przy sub-5% zmianie ceny, a naprawione RPC nie ma bezpiecznej ścieżki upgrade'u
z wcześniej zastosowanej migracji. Unit 7 pozostaje poza zakresem.

### Kontrole operatora

Brak ręcznych kontroli do oznaczenia jako wykonane.

### Decyzja gate

**BLOKUJE** — 2 P1, 1 P2, 0 P3. Unit 6 nie jest ukończony.

### Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 6` — napraw wyłącznie
zaakceptowane 2 P1 i 1 P2 z tego raportu; nie rozpoczynaj Unit 7.

## Wykonanie remediacji po re-review `c35f1d7`

- **Zakres:** wyłącznie 2 P1 i 1 P2 zaakceptowane w ograniczonym re-review
  `c35f1d7`; Unit 7 nie rozpoczęto.
- Snapshot grupy korzysta teraz wyłącznie z jawnego `internal_benchmark`/
  `internal_benchmarks`; brak tej projekcji nie tworzy snapshotu grupy i nie
  przenosi `price_median` produktu do domeny benchmarku.
- Historyczna migracja `202607290001_incremental_benchmark_commit.sql` została
  przywrócona byte-for-byte do stanu bazowego. Nowa migracja
  `202607300001_incremental_commit_partial_fixes.sql` wykonuje `CREATE OR
  REPLACE FUNCTION` dla aliasu JSON i no-mutation `partial`, dzięki czemu
  poprawka jest wdrażalna na bazach, które miały już Unit 6.
- `BenchmarkRebuildService` przyjmuje wyłącznie testowy hook sekcji krytycznej;
  test zatrzymuje scoped transaction po zdobyciu locka, uruchamia admina,
  potwierdza oczekiwanie i dopiero potem zwalnia lock.
- Weryfikacja: focused Unit 6/schema/RLS 30 PASS, lokalny runtime RPC 1 PASS
  po resecie z obiema migracjami, `py_compile`, `git diff --check` i pełna
  `bash scripts/check_fieldnote.sh` — PASS.
- **Status:** oczekuje ograniczonego re-review wyłącznie zmian z tego wykonania;
  nie zmieniono żadnego pliku poza zakresem Unit 6 i nie rozpoczęto Unit 7.

Następne polecenie:

`$dev-docs-review docs/active/fieldnote-stroller-mvp 6` — ograniczony re-review
wyłącznie poprawek z bieżącego commitu; nie poprawiaj kodu i nie rozpoczynaj
Unit 7.

## Ograniczony re-review remediacji `395abc9`

- **Data:** 2026-07-30
- **Zakres diffu:** `395abc9^..395abc9` (`c35f1d7..395abc9`)
- **Tryb:** `ograniczony re-review` wyłącznie trzech zaakceptowanych findings
  P1/P2 i ich regresji
- **Reviewers:** `correctness_reviewer`, `security_reviewer`,
  `test_reviewer`, `data_reviewer`
- **Gate:** `WYMAGA POPRAWEK`

### Kryteria akceptacji i zakres

Sprawdzono tylko: brak price leakage produktu do snapshotu grupy, rollout
poprawionego RPC bez modyfikowania zastosowanej migracji oraz deterministyczną
serializację scoped/admin. Unit 7 i UI są poza zakresem.

### Skonsolidowane findings

#### P2 — Upgrade migracji RPC nie ma wykonawczego testu historii istniejącej bazy

- **File:** `tests/test_supabase_schema_contract.py:79-87`; powiązana migracja
  `supabase/migrations/202607300001_incremental_commit_partial_fixes.sql`
- **Evidence:** test kontraktu sprawdza wyłącznie tekst historycznej i nowej
  migracji, a lokalny runtime test wykonano po `supabase db reset`, który
  tworzy świeżą bazę i stosuje obie migracje w jednym bootstrapie. Żaden test
  nie zaczyna od bazy, gdzie `202607290001` jest już wpisana w historii, ani
  nie aplikuje wyłącznie migracji `202607300001`.
- **Impact:** regress w kolejności/odkrywaniu migracji albo w replace RPC może
  przejść testy, mimo że środowisko wdrożone przed poprawką nie otrzyma
  no-mutation `partial` i aliasu JSON.
- **Scenario:** staging ma zastosowaną `202607290001`; deployment dodaje
  `202607300001`, ale migracja nie zostaje wykonana lub nie zastępuje funkcji.
- **Recommendation:** dodaj opt-in lokalny test upgrade'u: zastosuj historię
  do `202607290001`, potem wyłącznie `202607300001`, a następnie wykonaj RPC
  z prawidłowym snapshotem JSON i no-mutation `partial`.
- **Missing test:** opisany wykonawczy test upgrade'u bez `db reset` po
  zapisaniu wersji historycznej.

### Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | PASS | 0 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | findings | 1 P2 | 0 |
| data_reviewer | PASS | 0 | 0 |

### Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused Unit 6 + schema/RLS | PASS | `fieldnote-api/.venv/bin/python -m unittest tests/test_incremental_pipeline.py tests/test_incremental_benchmark_rebuild.py tests/test_supabase_schema_contract.py tests/test_rls_policy_contract.py` — 30 testów |
| Opt-in fenced RPC | PASS | `FIELDNOTE_SUPABASE_INTEGRATION=1 fieldnote-api/.venv/bin/python -m unittest tests.test_supabase_runtime_contract.SupabaseRuntimeContractTests.test_incremental_commit_rpc_fences_price_threshold_and_partial_without_snapshot -v` — 1 test |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` |
| Spójność diffu | PASS | `git diff --check c35f1d7..395abc9` |

### Bezpieczeństwo

`security_reviewer`: PASS. Nie wykryto nowego bypassu RLS, grantu RPC poza
`service_role`, wycieku sekretu ani regresji fencing/`SECURITY DEFINER`.

### Odchylenia od planu

Wszystkie trzy poprawki funkcjonalne są potwierdzone, lecz kryterium bezpiecznego
rolloutu wymaga jeszcze wykonawczego testu upgrade'u z istniejącą historią
migracji. Unit 7 pozostaje poza zakresem.

### Kontrole operatora

Brak ręcznych kontroli do oznaczenia jako wykonane.

### Decyzja gate

**WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3. Unit 6 nie jest ukończony.

### Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 6` — napraw wyłącznie
zaakceptowany P2 wykonawczego testu upgrade'u migracji; nie rozpoczynaj Unit 7.

## Wykonanie remediacji P2 po re-review `395abc9`

- **Zakres:** wyłącznie zaakceptowany P2 dotyczący wykonawczego upgrade'u
  migracji; Unit 7 nie rozpoczęto.
- Dodano opt-in test `test_incremental_commit_migration_upgrade_without_reset`.
  Test zachowuje wpis `202607290001`, usuwa tylko `202607300001`, instaluje
  jedno-statement baseline sentinel i uruchamia `supabase migration up
  --local --yes` bez resetu. Następnie przez PostgREST wykonuje no-mutation
  `partial` bez snapshotu oraz `succeeded` z JSON snapshotem, potwierdzając
  odpowiednio brak mutacji i zapis snapshotu.
- `finally` przywraca migrację następczą i usuwa unikalne fixture'y produktów,
  jobów, brandów i snapshotów. Nie zmieniono kodu produkcyjnego ani migracji.

### Weryfikacja wykonania

| Kontrola | Wynik |
|---|---|
| Focused Unit 6/schema/RLS | PASS — 30 testów |
| Opt-in runtime RPC + upgrade bez resetu | PASS — 2 testy |
| `py_compile tests/test_supabase_runtime_contract.py` | PASS |
| `git diff --check` | PASS |
| `bash scripts/check_fieldnote.sh` | PASS |

**Status:** poprawka P2 wykonana; dokumentacja oczekuje ograniczonego
re-review wyłącznie tej poprawki. Unit 6 nie jest jeszcze ukończony, Unit 7
pozostaje poza zakresem.

Następne polecenie:

`$dev-docs-review docs/active/fieldnote-stroller-mvp 6` — ograniczony re-review
wyłącznie poprawki testu upgrade'u; nie poprawiaj kodu i nie rozpoczynaj Unit 7.

## Ograniczony re-review remediacji `c3646b7`

- **Data:** 2026-07-30
- **Zakres diffu:** `395abc9..c3646b7`
- **Tryb:** `ograniczony re-review` wyłącznie P2 wykonawczego upgrade'u
  migracji i jego regresji
- **Reviewers:** `correctness_reviewer`, `security_reviewer`,
  `test_reviewer`, `data_reviewer`
- **Gate:** `GOTOWE DO KONTYNUACJI`

### Kryteria akceptacji i zakres

Sprawdzono tylko, czy baza z już zapisaną migracją `202607290001` otrzymuje
zastępczy RPC z `202607300001` bez resetu, a po upgrade wykonują się oba
poprawione flow: no-mutation `partial` i JSON snapshot. Nie sprawdzano Unit 7,
UI ani innych fragmentów Unit 6.

### Skonsolidowane findings

Brak zaakceptowanych findings P1, P2 i P3. Test instaluje jedno-statement
baseline sentinel, usuwa wyłącznie wpis historii `202607300001`, stosuje
następcę przez lokalne `supabase migration up`, a następnie wykonawczo
potwierdza oba wymagane RPC. Unikalne fixture'y są usuwane w `finally`.

### Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | PASS | 0 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | PASS | 0 | 0 |
| data_reviewer | PASS | 0 | 0 |

### Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused Unit 6 + schema/RLS | PASS | 30 testów |
| Opt-in fenced RPC + upgrade bez resetu | PASS | 2 testy lokalnego Supabase/PostgREST |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` |
| Spójność diffu | PASS | `git diff --check 395abc9..c3646b7` |

### Bezpieczeństwo

`security_reviewer`: PASS. Test korzysta wyłącznie z lokalnego service role,
nie zmienia grantów ani RLS, nie zapisuje sekretów i sprząta dane testowe.

### Odchylenia od planu

Brak. Poprawka domyka wymaganie bezpiecznego rollout'u sekwencyjnej migracji;
nie zmienia kodu produkcyjnego ani scope'u Unit 6.

### Kontrole operatora

Brak ręcznych kontroli do oznaczenia jako wykonane.

### Decyzja gate

**GOTOWE DO KONTYNUACJI** — 0 P1, 0 P2, 0 P3. Unit 6 jest ukończony.

### Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 7` — rozpocznij wyłącznie
Unit 7, jeżeli użytkownik zdecyduje o kontynuacji.
