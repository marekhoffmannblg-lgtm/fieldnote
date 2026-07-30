# Review — Unit 7: Wspólny Firecrawl i katalog konkurencji

- **Data:** 2026-07-30
- **Zakres diffu:** `696c19e..192a8a5`
- **Tryb:** `pełny review`
- **Reviewers:** `correctness_reviewer`, `security_reviewer`, `test_reviewer`, `data_reviewer`
- **Gate:** `BLOKUJE`

## Kryteria akceptacji unitu

- Wszystkie zewnętrzne adaptery używają wspólnego klienta Firecrawl v2 i
  wspólnego kontraktu `NormalizedSourceContent`/provenance.
- Klient obsługuje timeout, 429/backoff, usage/credits, max pages i cache bez
  fałszywego sukcesu.
- Oficjalny katalog producenta jest źródłem modeli; aktualne rekordy
  konkurencji są sklasyfikowane albo jawnie wykluczone.
- Tożsamość produktu to marka + model + konfiguracja: kolory nie tworzą
  produktu, konfiguracje 2w1/3w1 nie mogą się scalić.
- Testy adapterów i katalogu przechodzą offline, a Amazon/sklep nie omija
  quality gate.

## Zgodność z planem i zakresem

Diff tworzy klienta Firecrawl, adaptery Amazon/retailer, fixtures, discovery,
aliasy oraz preview API katalogu. Nie zmienia UI ani nie rozpoczyna Unit 8.

Wykonanie nie spełnia jeszcze powyższych kryteriów: realny niezaklasyfikowany
model przechodzi quality gate, normalny refresh katalogu API nie ma ścieżki do
skonfigurowanego źródła producenta, aliasy nie przetwarzają wariantów title-only
i część błędów providerów kończy tracebackiem.

## Skonsolidowane findings

### P1 — Provider failures crash instead of becoming retry/partial state

- **File:** `scripts/firecrawl_client.py:92-99`,
  `scripts/source_adapters.py:154-161`,
  `scripts/fetch_firecrawl_offer_pages.py:257`
- **Evidence:** klient łapie tylko `FirecrawlError`, więc `TimeoutError` z
  transportu wychodzi po pierwszej próbie. Ponadto fetcher nadal referuje
  usunięte importy `HTTPError` i `URLError`; przy `FirecrawlError` z wyczerpanego
  429 reprodukowalnie rzuca `NameError` przed zapisem kolejki.
- **Impact:** pojedynczy timeout/429 może przerwać research i nie zapisać
  kontrolowanego `error`/`partial`, zamiast zachować retry oraz provenance runu.
- **Scenario:** transport rzuca `TimeoutError`, albo `scrape_offer` zwraca
  wyczerpany błąd 429 dla pending oferty.
- **Recommendation:** normalizuj timeouty/transport failures do
  `FirecrawlError`, retryuj je w granicy klienta i obsłuż `FirecrawlError` w
  fetcherze z trwałym `record_error`.
- **Missing test:** injected timeout→success i exhausted timeout; injected 429
  w `fetch_pending_rows` z asercją `status=error`, zapisanego retry i wyniku
  `partial`/`failed` bez tracebacku.

### P1 — Quality gate katalogu zawsze przepuszcza niezaklasyfikowane modele

- **File:** `scripts/discover_manufacturer_catalog.py:107-113`,
  `fieldnote-api/services/brand_catalog_service.py:29-41`
- **Evidence:** oba raporty ustawiają `unclassified_real_products` na `0`, mimo
  że discovery oznacza rekord bez `benchmark_group` jako `review_required`.
  Reprodukcja dla realnego „Future stroller” daje `review_required=1` i
  `quality_gate=pass`; bieżący katalog zawiera pięć takich rekordów.
- **Impact:** katalog może zostać uznany za kompletny mimo aktywnych modeli bez
  wymaganej klasyfikacji, co łamie główne kryterium Unit 7.
- **Scenario:** oficjalny katalog zwraca nowy model bez grupy benchmarkowej.
- **Recommendation:** licz realne `review_required` jako niezaklasyfikowane i
  zwracaj `quality_gate=review`/stan częściowy, dopóki rekord nie zostanie
  sklasyfikowany lub jawnie wykluczony.
- **Missing test:** fixture z realnym modelem bez grupy dla discovery i
  `BrandCatalogService.current` musi zwracać niezerowy licznik oraz gate inny
  niż `pass`.

### P1 — Adminowy refresh katalogu nie może wykonać oficjalnego discovery

- **File:** `fieldnote-api/routers/brand_catalogs.py:31-37`,
  `fieldnote-api/services/brand_catalog_service.py:40-41`
- **Evidence:** router przekazuje jedynie opcjonalny `fixture_root`; zwykłe
  wywołanie nie przekazuje ani klienta, ani URL producenta i kończy się
  nieobsłużonym `ValueError` z `discover_catalog`. `configured_brands()` oraz
  `catalog_urls` z konfiguracji nie są użyte.
- **Impact:** administrator nie może odświeżyć autorytatywnego katalogu, więc
  nie powstaje wymagany preview modeli producenta.
- **Scenario:** admin wywołuje `POST /api/brand-catalogs/discover` dla
  Kinderkraft bez testowego fixture.
- **Recommendation:** waliduj markę względem `strollers.yaml`, wybieraj jej
  oficjalny URL i wstrzykuj wspólny klient; błędy konfiguracji/providerów
  zamieniaj na jawne 4xx lub `partial`, nie 500.
- **Missing test:** API/service test configured URL z klientem fixture,
  nieznana marka bez provider call oraz 429→`partial`.

### P1 — Alias identity łamie regułę kolorów i konfiguracji

- **File:** `scripts/normalize_product_aliases.py:45-69`
- **Evidence:** `alias_record()` buduje key z surowego `model` i tylko pola
  `configuration`; nie stosuje `normalize_alias()` i nie wyprowadza 2w1/3w1 z
  title. Reprodukowalnie `Combi Black` i `Combi White` tworzą dwa klucze, zaś
  title-only `Combi 2w1` oraz `Combi 3w1` scalają się w `brand|combi`.
- **Impact:** kolor tworzy fałszywe produkty, a konfiguracje nieporównywalne
  mogą scalać aliasy, źródła i evidence.
- **Scenario:** crawl producenta nie zawiera rozdzielonych pól modelu i
  konfiguracji, tylko nazwy kart.
- **Recommendation:** wyprowadzaj model bez koloru i rozpoznawaj konfigurację
  przed utworzeniem canonical key; przypadki niejednoznaczne pozostaw do
  manual merge, nigdy nie scalaj ich automatycznie.
- **Missing test:** title-only black/white scala się, a title-only 2w1/3w1
  pozostają dwoma produktami.

### P1 — Ścieżka PDF zapisuje HTML/markdown jako uszkodzony manual PDF

- **File:** `scripts/fetch_manufacturer_sources.py:185-194,250-276`
- **Evidence:** domyślny Firecrawl fetch zawsze zwraca tekstowe body i
  `Content-Type: text/html`; dla `--pdf-url` jest ono mimo to zapisywane jako
  `document.pdf`, a błąd parsera jest wyłącznie warningiem.
- **Impact:** uszkodzony snapshot manuala może zostać zachowany jako pobrany
  source i nie daje wiarygodnego provenance/evidence.
- **Scenario:** Firecrawl zwraca markdown dla URL instrukcji PDF.
- **Recommendation:** użyj jawnego artefaktu PDF/raw Firecrawl albo osobnego
  tekstowego snapshotu; waliduj sygnaturę PDF przed `document.pdf` i kończ
  manual jako `partial`/error, gdy artefakt nie jest dostępny.
- **Missing test:** markdown dla `pdf-url` nie tworzy `document.pdf`; fixture
  prawdziwego PDF zachowuje bytes i provenance.

### P2 — Quality gate dopuszcza kartę innego modelu z przypadkową wzmianką

- **File:** `scripts/source_adapters.py:295-304`
- **Evidence:** dopasowanie modelu sprawdza token w połączonym title i całym
  markdown. „NUBI 2 stroller compatible with NEBO” dla NEBO zwraca
  `model_match=True` oraz `accepted`.
- **Impact:** evidence i parametry innego modelu mogą zostać przypisane do
  produktu benchmarkowego.
- **Scenario:** karta Amazon/sklepu opisuje inny model, ale wymienia badany
  model jako kompatybilny akcesorium.
- **Recommendation:** wymagaj dokładnego modelu w tytule/zweryfikowanej
  identity, a wzmianki kompatybilności traktuj jako odmowę.
- **Missing test:** parametryczny Amazon/retailer fixture „other model,
  compatible with target” musi kończyć się `rejected`.

### P2 — Admin może użyć preview do odczytu dowolnego katalogu JSON hosta

- **File:** `fieldnote-api/routers/brand_catalogs.py:17-37`,
  `scripts/discover_manufacturer_catalog.py:83-94`
- **Evidence:** request-controlled `fixture_root` jest tylko rozwiązywany i
  sprawdzany przez `exists()`, po czym discovery rekurencyjnie odczytuje każde
  `*.json` i zwraca pola w odpowiedzi.
- **Impact:** przejęta lub błędnie użyta sesja admina może wyprowadzić treść
  czytelnych JSON z hosta, poza zakresem katalogu źródeł.
- **Scenario:** admin przesyła ścieżkę do katalogu runów/konfiguracji zamiast
  testowych fixtures.
- **Recommendation:** nie wystawiaj fixture path przez API; testowy root
  wstrzykuj serwerowo albo ogranicz go do stałego katalogu fixtures wraz z
  kontrolą symlinków i allowlistą zwracanych pól.
- **Missing test:** root poza allowlistą oraz symlink wychodzący poza nią
  zwracają 4xx bez zawartości JSON.

### P3 — non-blocking

Brak zaakceptowanych findings P3.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | findings | 5 P1 | 0 |
| security_reviewer | findings | 1 P2 | 1 P2 |
| test_reviewer | findings | 2 P1, 1 P2 (duplikaty skonsolidowane) | 1 P2 (subsumowany) |
| data_reviewer | findings | 2 P1 (duplikaty), 1 P2 (duplikat) | 0 |

Odrzucono uwagę o nieautoryzowanym `GET /api/brand-catalogs` w trybie
`legacy_readonly`: jest zgodna z istniejącym lokalnym kontraktem, natomiast w
trybie Supabase globalny guard Unit 4 wymaga sesji. Nie jest to regresja Unit 7.

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused Unit 7 | PASS | `python3 -m unittest tests/test_firecrawl_client.py tests/test_firecrawl_source_adapters.py tests/test_manufacturer_catalog_discovery.py tests/test_product_aliases.py` — 11 testów |
| API/auth regression | PASS | `fieldnote-api/.venv/bin/python -m unittest tests/test_fieldnote_api_contracts.py tests/test_auth_roles.py` — 27 testów |
| Spójność diffu | PASS | `git diff --check 696c19e..192a8a5` |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` (backend, checkery, frontend typecheck/test/build) |
| Failure paths Unit 7 | FAIL | reprodukcje timeoutu, 429 fetchera, unclassified catalogu oraz aliasów wykazały findings P1/P2 |

## Bezpieczeństwo

Nie znaleziono sekretu ani paid provider call w testach. Pozostaje P2 dla
request-controlled `fixture_root`; wymaga ograniczenia przed użyciem endpointu
admina w środowisku Supabase.

## Odchylenia od planu

W planie wymieniono modyfikację `fetch_targeted_model_offers.py` i
`manufacturer_pipeline.py`; diff pozostawia je bez zmian. Pośrednie użycie
klienta przez fetcher Allegro nie zastępuje wymaganej produkcyjnej ścieżki
oficjalnego discovery katalogu.

## Kontrole operatora

Brak ręcznych kontroli do oznaczenia jako wykonane.

## Decyzja gate

**BLOKUJE** — 5 P1, 2 P2, 0 P3. Unit 7 nie jest ukończony; Unit 8 pozostaje
poza zakresem.

## Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 7` — napraw wyłącznie
zaakceptowane 5 P1 i 2 P2 z tego raportu; nie rozpoczynaj Unit 8.

## Remediation execute — stan przed ograniczonym re-review

Wykonano wyłącznie siedem zaakceptowanych poprawek. Retry klienta normalizuje
timeouty/transport errors i kolejka persystuje `FirecrawlError`; quality gate
wylicza `unclassified_real_products`; admin discovery waliduje skonfigurowaną
markę, używa pierwszego `catalog_url` i ogranicza fixture root do
`fixtures/firecrawl/manufacturer`. Alias identity stripuje kolory i wyprowadza
2w1/3w1 z tytułu, adapter odrzuca kompatybilność innego modelu, a ścieżka PDF
sprawdza `%PDF` przed utworzeniem `document.pdf`. Fixture discovery filtruje
również rekordy do allowlisty pól katalogu przed klasyfikacją.

Weryfikacja wykonania: focused remediation suite — 21 PASS; `py_compile` — PASS;
`git diff --check` — PASS; `bash scripts/check_fieldnote.sh` — PASS. Zmieniono
wyłącznie kod/testy i dokumentację Unit 7. Nie rozpoczęto Unit 8.

Status review pozostaje **PENDING LIMITED RE-REVIEW**; ten wpis nie oznacza
jeszcze PASS ani zamknięcia findings. Następne polecenie:
`$dev-docs-review docs/active/fieldnote-stroller-mvp 7`.
