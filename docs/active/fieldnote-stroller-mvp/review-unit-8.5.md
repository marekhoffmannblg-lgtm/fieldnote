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
