# Review — Unit 3: Repozytoria Supabase i selektywna migracja

- **Data:** 2026-07-24
- **Zakres diffu:** `16e9371..e7b7443` (`feat: add supabase repositories and selective migration`)
- **Tryb:** pełny review
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, data_reviewer`
- **Gate:** `BLOKUJE`

## Kryteria akceptacji unitu

- 34 produktów Lionelo oraz poprawne provenance są migrowane idempotentnie.
- Legacy pozostaje read-only, zaś katalog trybu `supabase` korzysta z repozytorium i jest fail-closed bez konfiguracji.
- Placeholdery i błędne referencje są odrzucane oraz raportowane.

## Zgodność z planem i zakresem

Sprawdzono wyłącznie Unit 3 z commitu `e7b7443`; Unit 4 nie został rozpoczęty. Przełącznik katalogu API, klient PostgREST, repozytoria i migrator mieszczą się w zakresie, ale niżej opisane defekty uniemożliwiają spełnienie kryterium migracji.

## Skonsolidowane findings

### P1 — blocking

#### P1 — Migrator nie transformuje kanonicznego katalogu do kontraktu `products`

- File: `scripts/migrate_validated_state_to_supabase.py:20-26`
- Evidence: kanoniczny importer zapisuje 34 Lionelo z `scope="production"` i `status="refresh_recommended"` (`scripts/import_lionelo_strollers.py:84-89`), ale migrator rozpoznaje własny katalog tylko przez `scope == "lionelo"` lub prawdziwe `is_lionelo`. Przekazuje też status bez mapowania do enuma `active|eol|draft|archived` i dla brakującego `is_lionelo` wysyła pusty string zamiast boolean (`supabase/migrations/202607230001_core_catalog.sql:3-5,25-26`).
- Impact: wymagane 34 Lionelo zostaną odrzucone przez selekcję albo PostgREST; główny flow Unit 3 jest złamany.
- Scenario: kanoniczny rekord `scope=production`, bez `is_lionelo`, nie tworzy zgodnego rekordu `products`.
- Recommendation: jawnie mapować ownership, status oraz boolean do kontraktu Supabase przed upsertem.
- Missing test: fixture 34 rekordów w kanonicznym kształcie importera przechodzi migrację do repozytorium walidującego kontrakt tabeli.

### P2 — important

#### P2 — Tryb Supabase zapisuje nowe produkty wyłącznie do legacy katalogu

- File: `fieldnote-api/app.py:2917-2942`
- Evidence: `create_product()` zawsze używa `load_products()` i `ensure_catalog_product()`, a nie `CatalogRepository`; `frontend_catalog()` w trybie Supabase czyta tylko repozytorium.
- Impact: produkt utworzony przez API nie trafia do Supabase, znika z kolejnej listy, a legacy nie jest read-only.
- Scenario: `POST /api/products`, następnie `GET /api/products` przy `FIELDNOTE_DATA_MODE=supabase`.
- Recommendation: w Supabase upsertować brand i product przez repozytorium bez odczytu/zapisu legacy.
- Missing test: Supabase POST nie dotyka legacy i rekord jest widoczny w następnym list/detail.

#### P2 — Szczegóły produktu w trybie Supabase nadal czytają legacy provenance

- File: `fieldnote-api/app.py:2948-2966`
- Evidence: `get_product()` bezwarunkowo wywołuje `load_product_provenance(product_slug)`.
- Impact: detail po przełączeniu na Supabase może zwracać nieaktualne dane legacy i narusza granicę repozytoryjną.
- Scenario: `GET /api/products/<slug>` w Supabase odczytuje lokalne provenance.
- Recommendation: do czasu repozytorium provenance zwracać w tym trybie pustą projekcję albo użyć dedykowanego repozytorium.
- Missing test: sentinel legacy provenance nie jest wywoływany przez detail w Supabase.

#### P2 — Unit nie dostarcza wykonywalnej migracji zatwierdzonego stanu

- File: `scripts/migrate_validated_state_to_supabase.py:17-50`
- Evidence: `load_fixture()` i `migrate()` nie mają CLI/entrypointu, a commit nie zawiera wersjonowanego fixture'u 34 Lionelo wraz ze źródłami, links i evidence. Test używa danych syntetycznych w pamięci.
- Impact: zielone testy nie umożliwiają ani nie dowodzą migracji zatwierdzonego katalogu i provenance do pustego Supabase.
- Scenario: operator nie ma kanonicznego wejścia ani komendy importu, więc Supabase pozostaje puste.
- Recommendation: dodać śledzony input i entrypoint `load → migrate → audit` z raportem odrzuceń.
- Missing test: entrypoint na fixture uruchomiony dwukrotnie pozostawia 34 Lionelo i kontrolowane liczniki provenance.

#### P2 — Audit nie weryfikuje dokładnie 34 produktów Lionelo

- File: `scripts/audit_supabase_migration.py:3-4`
- Evidence: używa `report.products >= expected_lionelo`; licznik obejmuje konkurentów i duplikaty, nie distinct owned/Lionelo.
- Impact: 33 Lionelo i konkurent mogą uzyskać PASS.
- Scenario: payload z 33 Lionelo i jednym konkurentem daje `products == 34`.
- Recommendation: raportować distinct owned IDs osobno i wymagać dokładnie 34.
- Missing test: 33 Lionelo + konkurent oraz 35 Lionelo kończą audit wynikiem review/fail.

### P3 — non-blocking

Brak zaakceptowanych findings P3.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | P2 ×2 | 2 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | P2 ×2 | 2 | 0 |
| data_reviewer | P1 ×1, P2 ×1 | 2 | 0 |

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Testy Unit 3 | PASS | `fieldnote-api/.venv/bin/python -m unittest tests/test_fieldnote_api_contracts.py tests/test_supabase_repositories.py tests/test_selective_migration.py` — 23 tests |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` — backend, checkery i frontend typecheck/test/build |
| Czystość diffu | PASS | `git diff --check 16e9371..e7b7443` |

## Bezpieczeństwo

Security review: PASS. Service-role pozostaje po stronie API, brak konfiguracji jest fail-closed, błędy nie ujawniają sekretu; nie znaleziono obejścia RLS ani dostępu frontendu do klucza.

## Odchylenia od planu

Unit 4 nie został rozpoczęty. Aktualny Unit 3 wymaga naprawy wskazanych P1/P2.

## Kontrole operatora

Po poprawkach operator może wykonać migrację do lokalnego Supabase z zatwierdzonym fixturem; nie oznaczono jej jako wykonanej podczas tego review.

## Decyzja gate

**BLOKUJE** — 1 P1, 4 P2, 0 P3. Unit 3 nie może zostać oznaczony jako ukończony.

## Stan po naprawach

Poprawki P1/P2 są zapisane do ograniczonego re-review: kanoniczne rekordy Lionelo są mapowane do kontraktu Supabase, API Supabase nie dotyka legacy katalogu ani provenance, fixture jest wersjonowany, `run_migration` wykonuje migrację z audytem, a audit wymaga dokładnie 34 distinct Lionelo. Wykonano focused testy (27 PASS), parse JSON fixture, `git diff --check` oraz pełną offline bramkę (PASS). Ten wpis nie zmienia gate — wymaga niezależnego ograniczonego re-review.

## Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 3` — napraw wyłącznie zaakceptowany P1 i cztery P2, a następnie wykonaj ograniczony re-review Unit 3.

## Ograniczony re-review napraw — `c8ca42c^..c8ca42c`

- **Data:** 2026-07-24
- **Tryb:** ograniczony re-review
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, data_reviewer`
- **Gate:** `BLOKUJE`

### P1 — Fixture migruje syntetyczny katalog zamiast zatwierdzonych 34 Lionelo

- File: `fixtures/unit3/validated_state_v1.json:2-35`
- Evidence: fixture zawiera `product:lionelo:00:` … `product:lionelo:33:` oraz modele `00` … `33`, zamiast wersjonowanych stabilnych ID realnego katalogu, takich jak Amber/Mika/Layla. Audit sprawdza jedynie liczność.
- Impact: domyślna migracja może zakończyć się PASS i wypełnić Supabase fikcyjnym katalogiem — fałszywy sukces głównego flow.
- Scenario: operator uruchamia CLI bez `--input`; API Supabase pokazuje `Lionelo 00`, a nie katalog MVP.
- Recommendation: fixture/manifest oraz audit muszą używać dokładnego zatwierdzonego zbioru 34 realnych `product_id`.
- Missing test: zamiana realnych ID na `00..33` kończy audit wynikiem review/fail.

### P1 — Niezautoryzowany endpoint zapisuje dane przez service-role

- File: `fieldnote-api/app.py:2918-2936`
- Evidence: `POST /api/products` nie ma zależności sesji ani roli, a w trybie Supabase używa klienta z `SUPABASE_SERVICE_ROLE_KEY`, który omija RLS.
- Impact: dowolny klient mający dostęp do API może tworzyć marki i produkty mimo granicy analyst/admin.
- Scenario: niezalogowany klient wysyła poprawny POST przy `FIELDNOTE_DATA_MODE=supabase`.
- Recommendation: wymagać zweryfikowanego JWT i roli analyst/admin albo wyłączyć zapis Supabase do Unit 4.
- Missing test: brak sesji/viewer otrzymują 401/403, a zapis jest możliwy wyłącznie dla uprawnionej roli.

### P2 — Marka wielowyrazowa ma rozbieżny `brand_key`

- File: `fieldnote-api/app.py:2933-2935`, `fieldnote-api/repositories/catalog_repository.py:19-24`
- Evidence: API zapisuje `Cybex Gold` jako `cybex-gold`, lecz repozytorium wyszukuje `cybex gold`, bo payload nie przekazuje `brand_key`.
- Impact: utworzenie poprawnego produktu konkurencji kończy się błędem braku marki.
- Scenario: POST dla `brand="Cybex Gold"` w Supabase.
- Recommendation: stosować jeden canonical helper `brand_key` w API i repozytorium.
- Missing test: idempotentne utworzenie i odczyt marki wielowyrazowej.

| Reviewer | Wynik | Findings przyjęte |
|---|---|---:|
| correctness_reviewer | P1 ×1, P2 ×1 | 2 |
| security_reviewer | P1 ×1 | 1 |
| test_reviewer | PASS | 0 |
| data_reviewer | P1 ×1, P2 ×1 | 2 |

Ponowiono focused suite (27 PASS), `git diff --check c8ca42c^..c8ca42c` (PASS) i pełną offline bramkę (PASS). Finding fixture oraz brand-key zostały scalone. **Gate: BLOKUJE — 2 P1, 1 P2, 0 P3.**

## Stan po naprawie ograniczonego re-review

Naprawiono wyłącznie findings z powyższej sekcji: fixture ma realny expected set 34 Lionelo ze śledzonych specyfikacji; audit porównuje set, a nie samą liczność; zapis Supabase przez publiczny endpoint jest wyłączony do Unit 4; `brand_key` jest wspólny dla repozytorium. Focused suite: 29 PASS; JSON fixture, `git diff --check` i pełna offline bramka: PASS. Gate pozostaje do niezależnego ograniczonego re-review.

## Ograniczony re-review — `3d638b7^..3d638b7`

- **Data:** 2026-07-24
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, data_reviewer`
- **Gate:** `WYMAGA POPRAWEK`

Correctness, security i tests: PASS. Data review potwierdził realną zgodność obecnego fixture'u ze śledzonymi specyfikacjami (34/34), ale wykrył jeden finding:

### P2 — CLI audit ufa deklarowanej liście ID z wejściowego fixture

- File: `scripts/migrate_validated_state_to_supabase.py:64-66`
- Evidence: `run_migration()` przekazuje `expected_lionelo_product_ids` z dowolnego payloadu do `audit()`, zastępując kanoniczny zbiór z `data/internal_specs`.
- Impact: fixture z 34 syntetycznymi ID i własną zgodną listą może uzyskać PASS.
- Scenario: operator uruchamia CLI z `--input` wskazującym taki fixture.
- Recommendation: CLI ma zawsze używać kanonicznego zbioru specs albo odrzucać mismatch deklaracji fixture względem specs.
- Missing test: syntetyczny fixture z własną listą expected zwraca `review`.

Ponowiono focused suite (29 PASS), `git diff --check 3d638b7^..3d638b7` (PASS) oraz pełną offline bramkę (PASS). **Gate: WYMAGA POPRAWEK — 0 P1, 1 P2, 0 P3.**

## Stan po naprawie P2 CLI

`run_migration()` nie przekazuje już deklaracji expected z inputu do audytu; audit zawsze pobiera kanoniczny set śledzonych specyfikacji. Regresja z 34 syntetycznymi ID i własną deklaracją fixture kończy się `review`. Focused suite: 30 PASS; pełna offline bramka i `git diff --check`: PASS. Gate pozostaje do ograniczonego re-review.

## Ograniczony re-review — `c93ab1f^..c93ab1f`

- **Data:** 2026-07-24
- **Tryb:** ograniczony re-review wyłącznie poprawki P2 kanonicznego zbioru Lionelo
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, data_reviewer`
- **Gate:** `WYMAGA POPRAWEK`

### P2 — Kanoniczna walidacja następuje dopiero po zapisach migracji

- File: `scripts/migrate_validated_state_to_supabase.py:63-65`
- Evidence: `run_migration()` najpierw wywołuje `migrate()`, która wykonuje upserty produktów, źródeł, linków i evidence, a dopiero potem `audit(report)` porównuje `lionelo_ids` z kanonicznym zbiorem `data/internal_specs`.
- Impact: poprawnie sformatowany, lecz niekanoniczny fixture może zostać zapisany z użyciem service-role, po czym CLI zwróci `review`; operator dostaje wynik odrzucenia po częściowej mutacji docelowych danych.
- Scenario: `--input` zawiera 34 fałszywe ID Lionelo zamiast śledzonych specyfikacji. Migrator wykona upserty, następnie audit zwróci `review` i CLI zakończy się kodem 2.
- Recommendation: przed skonstruowaniem repozytoriów i pierwszym upsertem obliczyć eligible Lionelo z payloadu oraz porównać je z `expected_lionelo_ids()`; przy mismatch przerwać bez zapisu (alternatywnie całą operację objąć transakcją z rollbackiem).
- Missing test: fixture z niekanonicznymi ID zwraca `review` albo błąd **oraz** nie wywołuje żadnego `upsert_*` na fake repositories.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | PASS | 0 | 0 |
| security_reviewer | P2 ×1 | 1 | 0 |
| test_reviewer | PASS | 0 | 0 |
| data_reviewer | P2 ×1 | 1 (scalone z security) | 0 |

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused Unit 3/API | PASS | `fieldnote-api/.venv/bin/python -m unittest tests/test_selective_migration.py tests/test_supabase_repositories.py tests/test_fieldnote_api_contracts.py` — 30 tests |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` — backend, checkery i frontend typecheck/test/build |
| Czystość diffu | PASS | `git diff --check c93ab1f^..c93ab1f` |

## Decyzja gate

**WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3. Unit 3 pozostaje nieukończony; Unit 4 nie został rozpoczęty.

## Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 3` — napraw wyłącznie P2: wykonaj preflight kanonicznych ID przed każdym upsertem i dodaj regresję potwierdzającą brak zapisów dla niezgodnego fixture'u.

## Stan po naprawie P2 preflightu

`_canonical_preflight()` wylicza eligible Lionelo z payloadu i porównuje je z kanonicznym zbiorem `data/internal_specs` przed pierwszym upsertem. `main()` wykonuje tę kontrolę przed tworzeniem klienta Supabase i repozytoriów, a `run_migration()` utrzymuje ją także dla wywołań programistycznych. Regresja z syntetycznymi ID potwierdza status `review`, jawny powód `canonical_lionelo_set_mismatch` oraz brak zapisów w fake catalog/source. Focused suite: 30 PASS; `py_compile`, pełna offline bramka i `git diff --check`: PASS. Gate pozostaje do niezależnego ograniczonego re-review.

## Ograniczony re-review — `4dd87e1^..4dd87e1`

- **Data:** 2026-07-24
- **Tryb:** ograniczony re-review wyłącznie P2 preflightu kanonicznego zbioru
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, data_reviewer`
- **Gate:** `WYMAGA POPRAWEK`

### P2 — Brak wykonawczego testu preflightu ścieżki CLI

- File: `tests/test_selective_migration.py:59-67`
- Evidence: regresja wywołuje `run_migration()` z fake repositories, ale nie uruchamia `main(["--input", ...])`. Blok preflightu w `main()` jest osobną ścieżką, która ma zagwarantować brak konstrukcji `SupabaseClient` i repozytoriów.
- Impact: późniejszy refaktor może pominąć preflight w CLI, nadal zachować go w `run_migration()` i pozostawić testy zielone, mimo że błędny input inicjalizuje service-role klienta.
- Scenario: usunięcie warunku preflightu z `main()` przy pozostawieniu preflightu w `run_migration()`.
- Recommendation: utworzyć tymczasowy niekanoniczny fixture i testować `main(["--input", path])` z sentinelami dla `SupabaseClient.from_env`, `CatalogRepository` oraz `SourceRepository`; oczekiwany jest kod 2 i zero wywołań sentinelów.
- Missing test: CLI zwraca kod 2 przed konfiguracją klienta/repozytoriów dla niekanonicznego fixture'u.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | PASS | 0 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | P2 ×1 | 1 | 0 |
| data_reviewer | PASS | 0 | 0 |

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused Unit 3/API | PASS | `fieldnote-api/.venv/bin/python -m unittest tests/test_selective_migration.py tests/test_supabase_repositories.py tests/test_fieldnote_api_contracts.py` — 30 tests |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` — backend, checkery i frontend typecheck/test/build |
| Czystość diffu | PASS | `git diff --check 4dd87e1^..4dd87e1` |

## Decyzja gate

**WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3. Unit 3 pozostaje nieukończony; Unit 4 nie został rozpoczęty.

## Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 3` — napraw wyłącznie P2 wykonawczego testu preflightu CLI.

## Stan po naprawie P2 testu CLI

Dodano deterministyczny test `main(["--input", path])` z tymczasowym niekanonicznym fixturem. Podstawione moduły repozytoriów mają sentinele, które przerwałyby test przy konstrukcji `SupabaseClient` lub repozytoriów; test potwierdza kod 2, raport `review`, `canonical_lionelo_set_mismatch` i zerowe liczniki przed każdą mutacją. Focused suite: 31 PASS; `py_compile`, pełna offline bramka i `git diff --check`: PASS. Gate pozostaje do niezależnego ograniczonego re-review.
