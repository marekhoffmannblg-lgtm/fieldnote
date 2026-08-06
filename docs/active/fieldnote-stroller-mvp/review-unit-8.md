# Review — Unit 8: Audyt atrybutów i względny scoring wózków

- **Data:** 2026-08-06
- **Zakres diffu:** `b71a991^..b71a991` (`d4a8d1a..b71a991`)
- **Tryb:** `pełny review`
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, data_reviewer`
- **Gate:** `BLOKUJE`

## Kryteria akceptacji unitu

- Audyt obejmuje 21 atrybutów wózków i uzasadnia decyzję dla każdego pola.
- Scoring jest deterministyczny w czterech segmentach; wynik jest ograniczony
  do zgodnego `model + konfiguracja`.
- Brak danych obniża completeness, ale nie utility score przez imputację zera.
- Cena jest oddzielona od utility score; internal benchmark wymaga co najmniej
  trzech Lionelo, a competitive ma maksymalnie sześciu zgodnych uczestników.
- Wynik i semantyczne snapshoty są dostępne w działającym flow aplikacji.

## Zgodność z planem i zakresem

Zakres commitu obejmuje schema 21 pól, offline audit, normalizację/scoring,
serwisy internal/competitive/pricing, DTO oraz testy. Nie obejmuje jednak
`fieldnote-api/app.py`, przyrostowego commitu ani endpointów, mimo że plan
Unit 8 wskazuje `app.py` i storage jako modyfikowane ścieżki. Nowe serwisy są
wywoływane tylko przez testy, więc wynik nie trafia do runtime aplikacji.

## Skonsolidowane findings

### P1 — Nowy scoring i cena nie są podłączone do runtime ani trwałej historii

- **File:** `fieldnote-api/app.py:2660`, `fieldnote-api/app.py:2818`,
  `fieldnote-api/app.py:2836`; brak integracji z
  `fieldnote-api/services/{internal_benchmark_service,competitive_benchmark_service,pricing_service}.py`
  oraz `fieldnote-api/benchmark_storage.py:29`.
- **Evidence:** endpointy nadal zwracają legacy `benchmark_payload` i listy
  uczestników; `rg` znajduje `semantic_benchmark_payload` wyłącznie w jego
  definicji, a nowe serwisy są importowane wyłącznie przez testy Unit 8.
- **Impact:** użytkownik nie może otrzymać score, completeness, wkładów pól ani
  agregatu ceny; zmiana danych nie tworzy trwałego semantic snapshotu nowego
  kontraktu.
- **Scenario:** `GET /api/products/{slug}/benchmark` albo
  `GET /api/internal-benchmarks/{group}` po wdrożeniu Unit 8 nie wywołuje
  `score_products`.
- **Recommendation:** podłączyć serwisy do istniejących endpointów i
  przyrostowego commitu/snapshotów, zwracając wynik albo jawne
  `insufficient_data` bez regresji legacy.
- **Missing test:** API + scoped-commit test potwierdzający score,
  completeness, price summary oraz brak nowego semantic snapshotu przy
  identycznych danych.

### P1 — Brakujący atrybut jest liczony jak zero w utility score

- **File:** `scripts/benchmark_relative_scoring.py:68-89`.
- **Evidence:** `total_weight` jest sumą wag pól obecnych u dowolnego
  uczestnika, a produkt bez pola nie dostaje wkładu do licznika. Reprodukcja
  dwóch produktów z `one_hand_fold=Tak`, z `frame_weight` tylko w jednym,
  zwraca odpowiednio score `100.0` i `50.0`.
- **Impact:** niepełny konkurent jest systemowo zaniżany w rankingu, choć
  wymaganie Unit 8 stanowi, że brak obniża wyłącznie completeness.
- **Scenario:** produkt ze wszystkimi wspólnymi faktami, ale bez jednego pola
  liczbowego, przegrywa wyłącznie przez nieznaną wartość.
- **Recommendation:** normalizować score każdego produktu przez sumę wag pól,
  dla których ten produkt ma poprawną wartość; dla braku wszystkich pól zwrócić
  jawny stan bez score.
- **Missing test:** usunięcie jednego scored pola zachowuje score ze wspólnych
  faktów, a obniża wyłącznie completeness.

### P2 — Granica `model + konfiguracja` nie jest wymuszana konsekwentnie

- **File:** `fieldnote-api/services/internal_benchmark_service.py:10-14` oraz
  `fieldnote-api/benchmark_storage.py:69-107`.
- **Evidence:** internal service filtruje wyłącznie `benchmark_group`; ręczne
  tworzenie competitive manifestu także sprawdza wyłącznie grupę. Anchor 2w1
  i konkurent 3w1 z tą samą grupą mogą wejść do manifestu, a błędnie opisany
  rekord 3w1 może podnieść internal participant count.
- **Impact:** ranking może mieszać konfiguracje, łamiąc podstawową jednostkę
  benchmarku MVP.
- **Scenario:** 2w1 i 3w1 w tej samej grupie zapisują się razem przez endpoint
  manifestu lub uczestniczą wspólnie w internal normalizacji.
- **Recommendation:** wprowadzić kanoniczną konfigurację do scope'u internal i
  walidować ją przy zapisie/odczycie competitive manifestu; po filtracji
  ponownie stosować minimum trzech Lionelo.
- **Missing test:** odmowa 2w1 ↔ 3w1 w manifest API oraz wykluczenie 3w1 z
  internal benchmarku 2w1.

### P2 — `suspension` nie może dać dodatniego wkładu do score

- **File:** `config/categories/strollers.v1.yaml:27` oraz
  `scripts/benchmark_relative_scoring.py:26-43,71-72`.
- **Evidence:** schema określa `suspension` jako `text` z kierunkiem `binary`.
  Normalizacja tekstu zwraca napis, ale gałąź binary uznaje wyłącznie
  dosłowne `value is True`; `Tak`, `yes` i opis zawieszenia zawsze dostają `0`.
- **Impact:** jedno z pól `scored` stale zaniża wynik i nie różnicuje produktów.
- **Scenario:** `{"key":"suspension","value":"Tak"}` nie daje wkładu.
- **Recommendation:** zmienić pole na boolean albo dodać deterministyczną
  normalizację wartości zawieszenia do boolean.
- **Missing test:** `suspension=Tak` daje dodatni wkład, a `Nie` zerowy.

### P2 — Schema nie mapuje aliasów źródeł ani deklarowanych konwersji

- **File:** `config/categories/strollers.v1.yaml:1-28` i
  `scripts/benchmark_relative_scoring.py:46-54`.
- **Evidence:** schema ma wyłącznie kanoniczne klucze, a `attributes_map()`
  wykonuje exact lookup. Nie ma aliasów PL/EN ani wersjonowanej deklaracji
  konwersji, choć są wymagane przez plan Unit 8.
- **Impact:** dane konkurencji z naturalnymi etykietami źródłowymi będą
  wyglądały jak braki zamiast zasilać completeness i scoring.
- **Scenario:** `"waga stelaża"` albo `"frame weight"` nie trafia do
  `frame_weight`.
- **Recommendation:** zadeklarować aliasy i konwersje w schema, normalizować
  klucze wejściowe oraz odrzucać kolizje aliasów.
- **Missing test:** równoważne klucze PL/EN i kanoniczny dają identyczną wartość.

### P2 — Offline testy nie chronią kluczowych zachowań scoringu, cen i audytu

- **File:** `tests/test_relative_benchmark_scoring.py:16-38`,
  `tests/test_pricing_aggregation.py:9-20` i
  `tests/test_stroller_attribute_audit.py:9-17`.
- **Evidence:** test missing wymaga tylko `score >= 0`; nie ma asercji
  lower/higher rankingu, granicy dwóch Lionelo ani zgodnej konfiguracji. Cena
  nie sprawdza mediany/wyboru najnowszej obserwacji, a audit używa wyłącznie
  syntetycznego produktu, nie corpus 34 specyfikacji.
- **Impact:** odwrócenie kierunku liczbowego, usunięcie filtra konfiguracji,
  błąd mediany lub błędne wskazanie corpus mogą przejść zielone testy.
- **Scenario:** zmiana `lower` na `higher` dla frame weight nadal przechodzi
  obecne 15 testów.
- **Recommendation:** dodać deterministyczne regresje rankingów, granic,
  mediany/recency dedupe i audytu rzeczywistych 34 specyfikacji.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | 2 P1, 2 P2 | 4 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | 4 P2 | 1 skonsolidowany | 0 |
| data_reviewer | 1 P1, 3 P2 | 2 P1/P2 skonsolidowane | 0 |

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused Unit 8 | PASS, 15/15 | `test_stroller_attribute_audit`, `test_attribute_normalization`, `test_relative_benchmark_scoring`, `test_pricing_aggregation`, `test_semantic_snapshots` |
| Reprodukcja braku danych | FAIL oczekiwania produktu | komplet `frame_weight` → `100.0`; brak pola → `50.0` |
| `git diff --check b71a991^..b71a991` | PASS | bez błędów whitespace |
| `bash scripts/check_fieldnote.sh` | NIEUKOŃCZONE | hygiene rozpoczął się, następnie `tests/test_repository_hygiene.py` zawisł w `git show :<tracked-path>`; proces przerwano po braku postępu. Nie jest to wynik PASS ani finding Unit 8 bez osobnej reprodukcji. |

## Bezpieczeństwo

Security review: PASS. Diff nie dodaje endpointów, auth/RLS, storage,
providerów, sekretów ani wejść wykonujących kod/SQL/HTTP. Nie zmienia to P1
braku integracji runtime — jest to problem kompletności produktu, nie luka
bezpieczeństwa.

## Odchylenia od planu

- Plan wymagał integracji `fieldnote-api/app.py`; commit jej nie zawiera.
- Plan wymagał aliasów PL/EN i konwersji w konfiguracji; schema ich nie zawiera.
- Plan przewidywał audyt konkurentów; implementacja audytuje wyłącznie lokalne
  specyfikacje Lionelo. Należy objąć to testem i podczas naprawy ustalić
  deterministyczny, śledzony corpus konkurencji bez live providerów.

## Kontrole operatora

Brak nowych kontroli operatorskich. Firecrawl/OpenAI nie były uruchamiane.

## Decyzja gate

**BLOKUJE** — 2 P1, 4 P2, 0 P3. Unit 8 nie jest ukończony i Unit 8.5 nie
może zostać rozpoczęty.

## Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 8` — napraw wyłącznie
zaakceptowane 2 P1 i 4 P2 z tego raportu, następnie wykonaj ograniczony
re-review Unit 8. Nie rozpoczynaj Unit 8.5 ani Unit 9.
