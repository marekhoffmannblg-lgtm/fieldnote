# Review — Unit 8.5: Trwałe, pełne odświeżenie danych produktu

- **Data:** 2026-08-06
- **Zakres diffu:** `447673f..7ef02e5`
- **Tryb:** pełny review
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, data_reviewer`
- **Gate:** `BLOKUJE`

## Kryteria akceptacji unitu

Ręczny refresh jednego produktu ma przez trwały job zawsze wykonać świeży
Firecrawl Search i Scrape, zapisać prywatne raw/clean snapshoty oraz pełną
historię `job → źródło → snapshot → evidence → wartość`. Tylko `exact_match`
może przejść do ekstrakcji; wynik partial/failed/cancelled zachowuje
last-known-good. Identyczny refresh dodaje historię runu, ale nie duplikuje
snapshotu ani semantycznego benchmarku i aktualizuje wyłącznie istniejący scope.

## Zgodność z planem i zakresem

Sprawdzono wyłącznie commit `7ef02e5` i jego dokumentację aktywnego zadania.
Nie sprawdzano Unit 9 i nie zmieniano kodu. Diff dostarcza dependency-injected
prototyp oraz migrację, lecz nie podłącza go do routera, trwałej kolejki,
workera, repozytoriów, Storage ani fenced incremental commit.

## Skonsolidowane findings

### P1 — Brak wykonywalnego durable flow `product_refresh`

- File: `fieldnote-api/services/product_refresh_service.py:93`; brak integracji
  w routerze jobs, `JobService`, workerze, pipeline i repozytoriach.
- Evidence: wyszukiwanie `ProductRefreshService|product_refresh_runs` znajduje
  wyłącznie nowy serwis, migrację i test in-memory; istniejący endpoint tworzy
  nadal generic/legacy research job.
- Impact: analyst/admin nie może zlecić refreshu, a worker nie egzekwuje lease,
  cancel, limitów, usage ani scoped commit.
- Scenario: testy pamięciowe są zielone, choć API/worker nie mogą przeprowadzić
  odświeżenia ani utrwalić łańcucha po restarcie.
- Recommendation: podłączyć typed job przez router → JobService → queue →
  worker → repozytoria/Storage → fenced commit.
- Missing test: offline API-to-worker integration na fixtures po restarcie,
  bez wywołań płatnych providerów.

### P1 — Rzeczywisty `FirecrawlClient` daje fałszywy wynik częściowy

- File: `fieldnote-api/services/product_refresh_service.py:68-85`.
- Evidence: `_body` akceptuje wyłącznie `dict`, a wspólny
  `scripts/firecrawl_client.py` zwraca `FirecrawlResponse(data=...)`.
- Impact: w produkcji discovery jest puste i refresh kończy się
  `partial/no_exact_match`, choć provider zwrócił dane.
- Scenario: wstrzyknięcie istniejącego klienta Firecrawl nie uruchamia scrape.
- Recommendation: normalizować `FirecrawlResponse.data` oraz usage/status.
- Missing test: fixture transport wspólnego klienta Firecrawl w pełnym refreshu.

### P1 — Identyczny refresh gubi relację drugiego runu do snapshotu

- File: `supabase/migrations/202608060001_product_refresh_history.sql:13-25`;
  `fieldnote-api/services/product_refresh_service.py:51-57,142-149`.
- Evidence: `run_id` jest w tym samym wierszu co unikalny
  `(source_id, content_hash)`; drugi run nie może otrzymać własnej relacji i
  dostaje rekord pierwszego runu, lecz nadal kończy się sukcesem.
- Impact: historia nie daje wymaganego audytowalnego `run → source → snapshot`.
- Scenario: dwa identyczne odświeżenia mają dwa runy, ale tylko pierwszy jest
  powiązany ze snapshotem.
- Recommendation: rozdzielić deduplikowany snapshot od per-run `run_source`
  association, zapisywanej dla każdego fetchu.
- Missing test: dwa runy → dwa linki run-source i jeden snapshot.

### P2 — Deduplikacja semantyczna zależy od tożsamości obiektu Python

- File: `fieldnote-api/services/product_refresh_service.py:142-147`.
- Evidence: status `duplicate_snapshot` wynika z `persisted is not source`;
  adapter DB zwraca zwykle nowy dict także dla świeżego inserta.
- Impact: nowy snapshot może być błędnie uznany za duplikat i nie utworzyć
  semantycznego snapshotu.
- Recommendation: niech historia zwraca jawne `created`/snapshot ID.
- Missing test: adapter zwracający kopie dla insertu i asercje first/identical/changed.

### P2 — Niekanoniczne `source_id` nie spełnia FK historii

- File: `fieldnote-api/services/product_refresh_service.py:132`; migracja:17.
- Evidence: serwis używa gołego `offer_id` (np. `123456`), podczas gdy katalog
  używa `allegro:<offer_id>`; brak też upsertu `sources` i linku produktu.
- Impact: trwały insert może zakończyć się FK failure już po zapisie raw content.
- Recommendation: resolve/upsert kanonicznego źródła i `product_source_link`
  przed snapshotem, z transakcyjną kompensacją błędu.
- Missing test: kontrakt DB dla `allegro:<offer_id>`.

### P2 — Brak walidacji URL przed zewnętrznym scrape

- File: `fieldnote-api/services/product_refresh_service.py:114-128`.
- Evidence: identyfikacja sprawdza title, nie URL; dokładnie nazwany wynik może
  przekazać do provider'a dowolny scheme/host.
- Impact: zatruty wynik może zużyć budżet i skłonić adapter do pobrania
  niepożądanego adresu.
- Recommendation: HTTPS allowlist domen marketplace/producentów oraz blokada
  adresów prywatnych/rezerwowych i redirect escape.
- Missing test: exact-title `127.0.0.1`/obca domena nie wywołuje scrape.

### P2 — Raw evidence nie jest niezmienne przy tym samym clean hash

- File: `fieldnote-api/services/product_refresh_service.py:133-137`.
- Evidence: ścieżka raw zależy od hasha czystego textu i jest bezwarunkowo
  nadpisywana; różne raw JSON może mieć ten sam extracted text.
- Impact: historyczny raw dowód pierwszego runu może zostać zmieniony.
- Recommendation: wersjonować raw po hash payloadu i powiązać go ze snapshotem.
- Missing test: różny raw payload z tym samym clean text zachowuje oba artefakty.

### P2 — Brak wykonawczego RLS testu nowych tabel historii

- File: `supabase/migrations/202608060001_product_refresh_history.sql:28-33`.
- Evidence: nowe polityki nie występują w `test_rls_policy_contract.py` ani
  lokalnym teście PostgREST; suite Unit 8.5 używa wyłącznie pamięci.
- Impact: wymagane role i odmowy dla historii refreshu pozostają niezweryfikowane.
- Recommendation: rozszerzyć kontrakt i opt-in runtime test dla anon/viewer/
  analyst/admin oraz użytkownika z wymuszoną zmianą hasła.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | 3 P1 + 1 P2 | 3 P1 | 0 |
| security_reviewer | 2 P2 | 2 P2 | 0 |
| test_reviewer | 1 P1 + 2 P2 | 1 P1 + 2 P2 | 0 |
| data_reviewer | 1 P1 + 2 P2 | 1 P1 + 2 P2 | 0 |

Duplikaty dotyczące braku durable flow, run-source provenance, FK oraz
deduplikacji scalono powyżej. Nie przyjęto ogólnej uwagi o keyword identity
gate jako osobnego findingu: jest objęta wymaganym użyciem kanonicznego gate'u
i testem niebezpiecznego URL; implementacja ma zastąpić prosty fallback.

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| `tests/test_product_refresh_pipeline.py`, Firecrawl suites | PASS | 11 testów offline PASS |
| `python3 -m py_compile fieldnote-api/services/product_refresh_service.py` | PASS | bez błędów |
| `git diff --check 447673f..7ef02e5` | PASS | bez błędów whitespace |
| `bash scripts/check_fieldnote.sh` | NIEUKOŃCZONE | timeout/hang w istniejącym hygiene `git show :<tracked-path>` |

## Bezpieczeństwo

Nie znaleziono sekretów. RLS w migracji używa istniejących helperów ról, lecz
bez wykonawczego potwierdzenia. URL z niezaufanego discovery musi zostać
walidowany zanim trafi do Firecrawl.

## Odchylenia od planu

Wykonany commit jest wyłącznie fundamentem offline, mimo że checkboxy
implementacji/testu w tasks zostały zbyt szeroko oznaczone jako zakończone.
Pełny durable workflow nie został dostarczony.

## Kontrole operatora

Nie wykonywano live smoke ani płatnych wywołań.

## Decyzja gate

**BLOKUJE** — 3 P1, 5 P2, 0 P3. Unit 8.5 pozostaje `partial` i nie jest
ukończony. Unit 9 nie został rozpoczęty.

## Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 8.5` — napraw wyłącznie
zaakceptowane 3 P1 i 5 P2 z tego raportu.

---

## Ograniczony re-review `7ef02e5..cf6e2ed` (`2026-08-06`)

Sprawdzono wyłącznie remediation poprzednich findings oraz ich regresje.
Nie sprawdzano Unit 9 i nie zmieniano kodu.

### Skonsolidowane pozostałe findings

### P1 — Durable flow `product_refresh` nadal nie jest wykonywalny

- File: brak integracji serwisu w `routers/jobs.py`, `job_service.py`,
  `worker.py`, `pipeline_service.py` i repozytoriach.
- Evidence: typed job nie jest tworzony ani odbierany przez workera.
- Impact: użytkownik nie może przejść przez API → kolejkę → lease/cancel →
  worker → fenced commit; historia nie przetrwa restartu.
- Recommendation: wdrożyć trwały typed job i test API-to-worker na fixtures.

### P1 — Relacja `run → snapshot` nie spełnia własnego kontraktu migracji

- File: `product_refresh_service.py:158-165`; migracja:27-34.
- Evidence: tabela linków wymaga `snapshot_id NOT NULL`, a serwis przekazuje
  tylko source/hash/paths; `append_source` nie zwraca UUID snapshotu.
- Impact: rzeczywisty adapter nie utworzy drugiego trwałego linku do
  deduplikowanego snapshotu.
- Recommendation: atomowy create-or-reuse snapshot zwraca UUID i zapisuje
  per-run link z tym UUID.

### P2 — Custom identity gate omija URL allowlistę

- File: `product_refresh_service.py:176-188`.
- Evidence: wstrzyknięty gate zwraca przed walidacją URL; `exact_match` może
  dopuścić obcy lub prywatny host do scrape.
- Recommendation: walidować URL niezależnie od wyniku identity gate i dodać
  regresję z permissive gate.

### P2 — Canonical source nie jest resolve/upsertowany przed FK

- File: `product_refresh_service.py:144-158`; migracja:16.
- Evidence: fallback tworzy string `allegro:<offer_id>`, ale nie zapisuje
  `sources` ani `product_source_links`.
- Recommendation: transakcyjnie resolve/upsert źródło i link produktu przed
  snapshotem oraz dodać test lokalnego PostgreSQL.

### P2 — Drugi raw payload nie ma per-run durable provenance

- File: serwis:149-165; migracja:20-33.
- Evidence: drugi raw artefakt ma ścieżkę, ale deduplikowany snapshot trzyma
  tylko jedną, a run-source nie ma artifact ID.
- Recommendation: dodać per-fetch artefakt/evidence link do runu i test dwóch
  raw payloadów z tym samym clean textem.

### P2 — Brakuje asercji świeżego Search i Scrape dla obu runów

- File: `tests/test_product_refresh_pipeline.py:29-37`.
- Evidence: provider liczy wywołania, lecz test ich nie asercuje.
- Recommendation: wymusić dwa Search i dwa Scrape dla dwóch refresh runów.

### P2 — Brak wykonawczego RLS testu nowych tabel

- File: migracja:36-44; brak referencji w suite RLS/runtime.
- Evidence: nowe tabele są testowane wyłącznie adapterem pamięciowym.
- Recommendation: dodać contract i opt-in PostgREST test dla anon/viewer/
  analyst/admin/must-change-password.

### Wyniki reviewerów ograniczonego re-review

| Reviewer | Wynik | Findings przyjęte |
|---|---|---:|
| correctness_reviewer | 2 P1 + 3 P2 | 2 P1 + 3 P2 |
| security_reviewer | 2 P2 | 2 P2 |
| test_reviewer | 1 P1 + 3 P2 | scalone |
| data_reviewer | 1 P1 + 3 P2 | scalone |

### Testy re-review

- `tests/test_product_refresh_pipeline.py`, `test_firecrawl_client.py` i
  `test_firecrawl_source_adapters.py`: **14 PASS**.
- `python3 -m py_compile fieldnote-api/services/product_refresh_service.py`:
  PASS.
- `git diff --check 7ef02e5..cf6e2ed`: PASS.

### Decyzja gate re-review

**BLOKUJE** — **2 P1, 5 P2, 0 P3**. Poprzedni P1 dla formatu
`FirecrawlResponse` i P2 dla tożsamości obiektu zostały zamknięte. Unit 8.5
pozostaje `partial`; Unit 9 nie został rozpoczęty.

## Remediation execution `cf6e2ed..HEAD` (`2026-08-06`)

Dodano typed job/endpoint, worker branch bez `--resume`, Supabase
Storage/history adapter, snapshot UUID links, canonical source upsert,
allowlist przed custom gate oraz schema contracts i worker/job regressions.
Focused verification: **32 PASS**, `py_compile` PASS, `git diff --check` PASS.
Pełny `check_fieldnote.sh` ponownie nie ukończył się w 20 s na istniejącym
hygiene `git show`; runtime PostgREST/RLS i fenced scoped commit pozostają
nieoznaczone jako PASS. Unit nadal `partial`; wymagany jest kolejny ograniczony
review po tym commicie.

---

## Ograniczony re-review `cf6e2ed..0c8ec07` (`2026-08-06`)

Review objął wyłącznie ostatnią remediation. Correctness reviewer został
uruchomiony; security, tests i data wykonano jako **single-agent fallback** z
powodu wyczerpanego limitu aktywnych subagentów. Nie zmieniano kodu ani nie
rozpoczęto Unit 9.

### P1 — Worker zmienia udany refresh w `failed` po zapisaniu side effects

- File: `fieldnote-api/worker.py:55-62`,
  `fieldnote-api/services/benchmark_commit_service.py:45-47`,
  `pipeline_service.py:42-49`.
- Evidence: refresh zwraca `succeeded` bez `scoped_commit`; domyślny
  `BenchmarkCommitService` dla sukcesu wymaga tego envelope i rzuca błąd.
  Worker zapisuje wtedy `failed` już po uploadzie i historii źródeł.
- Impact: główny flow nigdy nie kończy się sukcesem, a użytkownik dostaje
  sprzeczny stan trwałych artefaktów i failed job.
- Recommendation: refresh ma albo zbudować fenced scoped commit, albo worker
  ma terminalizować go kontrolowanym `partial/no_mutation` bez false failure.
- Missing test: `ResearchWorker._run` z product_refresh i realnym committerem.

### P1 — Refresh nie aktualizuje faktów, evidence ani scoped benchmarku

- File: `product_refresh_service.py:137-172`; brak integracji z ekstrakcją,
  evidence/candidates i `BenchmarkCommitService` envelope.
- Evidence: service jedynie zapisuje content i zwraca listę źródeł; wynik nie
  zawiera wartości, quality gate ani `scoped_commit`.
- Impact: workflow nie realizuje celu Unit 8.5 „dane → fakty → istniejący scope
  benchmarkowy”, mimo że może wykonać zewnętrzny refresh.
- Recommendation: uruchomić deterministyczną ekstrakcję, ograniczone OpenAI
  dla braków, evidence/candidates oraz fenced commit tylko scope produktu.

### P2 — Limity i cancel nie są przekazywane do refresh providerów

- File: `pipeline_service.py:39-49`; `product_refresh_service.py:111-172`.
- Evidence: branch refresh nie przekazuje `RefreshLimits` z jobu ani nie czyta
  cancel-control file; używa domyślnego `max_candidates=20` i może fetchować
  mimo limitu/cancel.
- Impact: job może zużyć więcej stron/kredytów niż limit i nie kończyć się
  prawdziwym statusem partial/cancelled.
- Recommendation: przekazać limity oraz cancel check do serwisu przed każdym
  search/scrape, zapisać usage providerów i mapować przekroczenia na partial.

### P2 — Runtime RLS/Storage nie jest wykonawczo sprawdzone

- File: `tests/test_rls_policy_contract.py`; brak testu PostgREST dla tabel
  `product_refresh_*`.
- Evidence: dodano wyłącznie analizę tekstu migracji; pełny test lokalnego
  Supabase nie został uruchomiony.
- Impact: polityki w runtime pozostają niepotwierdzone dla anon/viewer/analyst
  i użytkownika z wymuszoną zmianą hasła.
- Recommendation: dodać opt-in test PostgREST/Storage po uruchomieniu Supabase.

### Testy re-review

- Focused refresh/job/Firecrawl/schema/RLS contract: **32 PASS**.
- `py_compile` zmienionych modułów i `git diff --check cf6e2ed..0c8ec07`:
  PASS.
- Pełny `bash scripts/check_fieldnote.sh`: nieukończony po 20 s przez znane
  zawieszenie hygiene na `git show`.

### Decyzja gate re-review

**BLOKUJE — 2 P1, 2 P2, 0 P3.** Unit 8.5 pozostaje `partial`; Unit 9 nie
został rozpoczęty. Następny krok: `$dev-docs-execute
docs/active/fieldnote-stroller-mvp 8.5` wyłącznie dla tych 2 P1 i 2 P2.

## Remediation execution `0c8ec07..HEAD` (`2026-08-06`)

Worker mapuje refresh bez `scoped_commit` na kontrolowany `partial/no_mutation`;
serwis przyjmuje limity i callback anulowania przed Search/Scrape oraz zwraca
deterministyczne evidence/excerpt i kandydata pola. Pozostają P1: pełna
ekstrakcja faktów, ograniczone OpenAI i fenced scoped commit; P2: wykonawczy
PostgREST/Storage RLS nowych tabel historii.

Weryfikacja: 32 focused testy, `py_compile` i `git diff --check` PASS. Pełny
`bash scripts/check_fieldnote.sh` przerwany na znanym zawieszeniu hygiene przy
`git show :<tracked-path>`. Gate: **BLOKUJE — 1 P1, 1 P2, 0 P3**. Unit 8.5
pozostaje partial, Unit 9 nie rozpoczęto. Następny krok:
`$dev-docs-review docs/active/fieldnote-stroller-mvp 8.5`.

---

## Ograniczony re-review `0c8ec07..8b766a5` (`2026-08-06`)

- **Tryb:** ograniczony re-review ostatniej poprawki; bez zmian kodu i bez Unit 9.
- **Reviewers:** `correctness_reviewer`, `test_reviewer`; security wykonano jako
  single-agent fallback, ponieważ limit aktywnych subagentów uniemożliwił
  osobną falę. `data_reviewer` nie był wymagany dla tego diffu.
- **Gate:** `BLOKUJE`.

### Skonsolidowane findings

### P1 — Konfiguracja produktu nie trafia do durable refresh job

- File: `fieldnote-api/services/job_service.py:68-78`; `fieldnote-api/services/pipeline_service.py:49-53`.
- Evidence: JobService zapisuje brand/model, ale pomija `product.configuration`; pipeline otrzymuje pustą konfigurację.
- Impact: job 3w1 może utrwalić ofertę 2w1 tego samego modelu.
- Recommendation: utrwalać kanoniczną konfigurację i dodać kontrakt API → job → pipeline odrzucający mismatch 2w1/3w1.

### P1 — Timeout i cancellation nie ograniczają wywołań providera

- File: `fieldnote-api/services/pipeline_service.py:44-60`; `fieldnote-api/services/product_refresh_service.py:121-181`.
- Evidence: `timeout_seconds` jest przekazany, ale nigdzie nieodczytany; cancel działa tylko między wywołaniami i kończy jako `partial`.
- Impact: zawieszony Search/Scrape może przekroczyć limit jobu i blokować slot workera; anulowanie w trakcie ostatniego Scrape może kończyć się sukcesem.
- Recommendation: wprowadzić deadline/provider timeout lub killable process i terminalizować potwierdzone anulowanie jako `cancelled`.

### P1 — Brak faktów, ograniczonego OpenAI i fenced scoped commit

- File: `fieldnote-api/services/product_refresh_service.py:172-181`.
- Evidence: wynik zawiera pojedynczy `product_description` candidate, bez kanonicznych faktów, quality gate ani `scoped_commit`.
- Impact: odświeżenie nie aktualizuje danych produktu ani benchmarku zgodnie z celem Unit 8.5.
- Recommendation: deterministycznie wyekstrahować fakty, użyć OpenAI tylko dla braków/niejednoznaczności i utworzyć fenced commit ograniczony do scope.

### P2 — Brakuje regresji dla workerowego partial i pozytywnego limitu/cancel

- File: `tests/test_product_refresh_worker_contract.py`; `tests/test_product_refresh_pipeline.py:93-101`.
- Evidence: test nie uruchamia `ResearchWorker` dla typed refreshu bez envelope; limit jest testowany jako zero, a cancel tylko przed Search.
- Impact: odwrócenie kontroli workerowej, off-by-one limitu lub usunięcie checku między Scrape nie zostałoby wykryte.
- Recommendation: dodać offline test worker `partial/no_mutation`, dwóch ofert przy `max_pages=1` oraz cancel po pierwszym Scrape.

### P2 — Brak wykonawczego PostgREST/Storage RLS nowych tabel historii

- File: `supabase/migrations/202608060001_product_refresh_history.sql`.
- Evidence: testy obejmują kontrakt tekstowy, ale nie requesty anon/viewer/analyst/admin do tabel `product_refresh_*` i prywatnych bucketów.
- Impact: runtime polityki historii i Storage są niepotwierdzone.
- Recommendation: dodać opt-in lokalny test Supabase/PostgREST/Storage.

### Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | 2 P1 | 2 P1 | 0 |
| security (single-agent fallback) | 1 P2 | 1 P2 | 0 |
| test_reviewer | 1 P1, 3 P2 | 1 P1, 1 P2 | 2 (duplikaty) |

### Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| focused refresh/worker/Firecrawl/schema/RLS | PASS | 33 testy offline |
| dodatkowy focused worker/job suite test reviewer | PASS | 29 testów offline |
| `py_compile` zmienionych modułów | PASS | bez błędów |
| `git diff --check 0c8ec07..8b766a5` | PASS | bez whitespace errors |
| `bash scripts/check_fieldnote.sh` | NIEUKOŃCZONE | znane zawieszenie hygiene `git show` |

### Bezpieczeństwo i decyzja gate

Nie znaleziono sekretów ani nowej regresji allowlisty URL. Runtime RLS/Storage
pozostaje nieudowodnione wykonawczo. **BLOKUJE — 3 P1, 2 P2, 0 P3.** Unit 8.5
pozostaje partial; Unit 9 nie został rozpoczęty.

Następny krok: `$dev-docs-execute docs/active/fieldnote-stroller-mvp 8.5` — napraw wyłącznie pięć zaakceptowanych findings z tej sekcji.

---

## Remediation execution `8b766a5..HEAD` (`2026-08-06`)

Naprawiono wszystkie pięć findingów z poprzedniej sekcji: configuration jest w
typed job payload; provider Search/Scrape ma bounded deadline i cancel po
Scrape; wynik tworzy deterministyczne fakty/evidence oraz scoped envelope;
doszły regresje worker/cap/mid-run cancel/timeout; dodano opt-in PostgREST/
Storage test trzech tabel historii.

Weryfikacja: **45 testów, 36 PASS, 9 skipped** (runtime Supabase), py_compile i
git diff-check PASS. Pełny `bash scripts/check_fieldnote.sh` zatrzymuje się na
znanym zawieszeniu hygiene `git show`; `supabase status` nie uruchamia się w
sandboxie przez zapis telemetry poza workspace. Unit 8.5 pozostaje **partial**
do runtime verification i ograniczonego re-review; Unit 9 nie rozpoczęto.

Następny krok: `$dev-docs-review docs/active/fieldnote-stroller-mvp 8.5`.

---

## Ograniczony re-review `8b766a5..3745c45` (`2026-08-06`)

- **Tryb:** ograniczony re-review remediation; kod nie był zmieniany, Unit 9 nie został rozpoczęty.
- **Reviewers:** `correctness_reviewer`, `test_reviewer`; security i data: single-agent fallback z powodu limitu aktywnych agentów.
- **Gate:** `BLOKUJE`.

### P1 — Placeholder tworzy fałszywy snapshot benchmarku grupy

- File: `fieldnote-api/services/product_refresh_service.py:224-232`; `fieldnote-api/services/benchmark_commit_service.py:_snapshots`.
- Evidence: refresh emituje `semantic_benchmark` zawierający tylko configuration i bieżący product_id. Commit service interpretuje to jako realną projekcję internal benchmarku i zapisuje snapshot grupy.
- Impact: refresh jednego produktu nadpisuje historię grupy snapshotem bez pozostałych uczestników, scoringu i cen.
- Scenario: grupa 3 modeli 3w1 dostaje snapshot z wyłącznie odświeżonym produktem.
- Recommendation: nie emitować benchmark projection bez pełnego istniejącego scope albo przebudować go przyrostowo z pełnym participant setem.

### P1 — Timeout nie zatrzymuje kosztownej operacji providera

- File: `fieldnote-api/services/product_refresh_service.py:117-139`.
- Evidence: timeout zwraca wynik z daemon thread, ale wywołanie Firecrawl nadal działa w tle.
- Impact: kolejne joby mogą tworzyć kolejne płatne wywołania mimo terminalizacji timeoutów, obchodząc limit współbieżności/kosztu.
- Recommendation: przekazać deadline do transportu albo uruchamiać refresh w killable process.

### P1 — Ekstrakcja nie spełnia pełnego kontraktu faktów/OpenAI

- File: `fieldnote-api/services/product_refresh_service.py:108-114,224-232`.
- Evidence: extractor rozpoznaje wyłącznie wagę, a wynik nie ma strategii uzupełnienia braków/niejednoznaczności przez ograniczone OpenAI.
- Impact: refresh nie dostarcza wymaganego pełnego zestawu kanonicznych faktów produktu.
- Recommendation: użyć istniejącego schematu/ekstraktora deterministycznego i kontrolowanego fallbacku AI tylko dla nierozstrzygniętych pól.

### P2 — Cancellation ma niespójny terminal status

- File: `fieldnote-api/services/product_refresh_service.py:161-189`.
- Evidence: cancel przed Search i między Scrape zwraca `partial`, a po Scrape `cancelled`.
- Impact: historia nie odróżnia konsekwentnie działania operatora od częściowego błędu.
- Recommendation: każdy potwierdzony cancel kończy się `cancelled` i ma regresje dla obu momentów.

### P2 — Brak pełnego kontraktu łańcucha fenced commit

- File: `tests/test_product_refresh_worker_contract.py`.
- Evidence: testy oddzielnie sprawdzają payload i fallback partial, ale nie przeprowadzają prawdziwego envelope przez pipeline, worker i committer.
- Impact: scope/configuration/participants mogą zostać zgubione lub poszerzone bez czerwonego testu.
- Recommendation: dodać offline adapter-chain test exact product/configuration/participants i brak snapshotu niezwiązanej grupy.

### P2 — Runtime test nie obejmuje faktycznych bucketów i wszystkich ról

- File: `tests/test_supabase_runtime_contract.py:322-355`.
- Evidence: nowy test sprawdza PostgREST tylko dla viewer/analyst; nie wykonuje Storage `source-raw`/`source-clean`, anon, read ani must-change-password.
- Impact: właściwe ścieżki artefaktów refreshu pozostają bez wykonawczego RLS testu.
- Recommendation: rozszerzyć opt-in test o te buckety i role.

### Wyniki i weryfikacja

| Reviewer | Wynik |
|---|---|
| correctness_reviewer | 2 P1, 1 P2 |
| test_reviewer | 1 P1, 2 P2 |
| security/data fallback | potwierdzony brak runtime Storage/RLS |

- focused suite: **45 testów, 36 PASS, 9 skipped**;
- `py_compile` i `git diff --check 8b766a5..3745c45`: PASS;
- pełny gate: nieukończony na znanym hygiene `git show`.

### Decyzja gate

**BLOKUJE — 3 P1, 3 P2, 0 P3.** Unit 8.5 pozostaje partial. Następny krok:
`$dev-docs-execute docs/active/fieldnote-stroller-mvp 8.5` — napraw wyłącznie
sześć findingów z tej sekcji.

---

## Remediation execution `3745c45..HEAD` (`2026-08-06`)

Naprawiono scope benchmarku (brak placeholderowej projekcji grupy), timeout
transportu Firecrawl bez daemon thread, spójne `cancelled`, pełny offline
kontrakt fenced commit oraz opt-in RLS/Storage dla właściwych bucketów i ról.
Pozostaje P1 pełnej ekstrakcji kanonicznych faktów i ograniczonego fallbacku
OpenAI; nie wywoływano płatnego API.

Weryfikacja: **46 testów, 37 PASS, 9 skipped**, py_compile i git diff-check
PASS. Pełny check_fieldnote.sh zatrzymał się na znanym hygiene `git show`.
Unit pozostaje partial; następny krok: `$dev-docs-review
docs/active/fieldnote-stroller-mvp 8.5`.
