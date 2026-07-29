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
