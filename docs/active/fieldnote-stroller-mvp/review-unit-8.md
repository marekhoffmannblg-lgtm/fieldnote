# Review — Unit 8: Audyt atrybutów i względny scoring wózków

- **Data:** 2026-08-06
- **Zakres diffu:** ograniczony re-review `0b985d0^..0b985d0`
- **Tryb:** `re-review`
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, data_reviewer`
- **Gate:** `BLOKUJE`

## Kryteria akceptacji unitu

- Audyt obejmuje 21 atrybutów i scoring jest deterministyczny w czterech
  segmentach.
- Jednostką porównania pozostaje `model + konfiguracja`.
- Brak danych obniża completeness, a nie utility score; cena jest osobnym
  wymiarem.
- Internal benchmark wymaga co najmniej trzech Lionelo; competitive używa
  zatwierdzonego, zgodnego składu i maksymalnie sześciu uczestników.
- Wynik, cena i semantic snapshot odnoszą się do tego samego, trwałego scope.

## Zakres ograniczonego re-review

Sprawdzono wyłącznie naprawy poprzednich 2 P1 i 4 P2 z pełnego review Unit 8:
runtime/commit scoringu i cen, per-product denominator, konfigurację,
`suspension`, aliasy/konwersje oraz regresje. Nie sprawdzano Unit 8.5 ani
Unit 9 i nie zmieniano kodu.

## Skonsolidowane findings

### P1 — Trwały semantic snapshot nadal miesza konfiguracje

- **File:** `scripts/run_model_research_pipeline.py:151-168` oraz
  `scripts/benchmark_relative_scoring.py:127-132`.
- **Evidence:** projection scoped commit zbiera wszystkie modele w tym samym
  `benchmark_group`, a `score_products()` również filtruje wyłącznie po grupie.
  Pole `configuration` jest przenoszone do kandydata, ale nie jest używane do
  filtra przed scoringiem. `BenchmarkCommitService` zapisuje ten projection
  jako durable benchmark-group snapshot.
- **Impact:** refresh 2w1 może trwale zapisać ranking znormalizowany względem
  3w1/4w1, łamiąc podstawową jednostkę benchmarku i provenance snapshotu.
- **Scenario:** grupa zawiera 2w1 oraz 3w1 z innymi wagami; refresh 2w1
  tworzy `semantic_benchmark` obejmujący oba produkty.
- **Recommendation:** wyprowadzić i znormalizować konfigurację produktu scope,
  filtrować kandydatów przed scoringiem i dodać konfigurację oraz participant
  IDs do payloadu/hashu snapshotu.
- **Missing test:** mixed-config fixture dla `scoped_commit_payload` potwierdza
  wyłącznie uczestników konfiguracji odświeżanego produktu.

### P1 — Detail competitive benchmarku liczy inny skład niż zapisany manifest

- **File:** `fieldnote-api/app.py:1692-1714,2775-2797`.
- **Evidence:** detail poprawnie zwraca `participant_product_ids` z manifestu,
  ale wywołuje `runtime_semantic_benchmark()` bez tych IDs. Helper dobiera
  wszystkich runtime kandydatów z grupy, a service wybiera własne pierwsze
  sześć; cena także używa wszystkich zgodnych produktów.
- **Impact:** API może wyświetlić ręcznie zatwierdzonych konkurentów, a score,
  pozycje i cena odnoszą się do innych produktów. Wynik jest niereprodukowalny
  z trwałej relacji benchmarku.
- **Scenario:** manifest wskazuje `c7` i `c8`, ale istnieje sześć wcześniej
  sortowanych kandydatów; response pokazuje `c7/c8`, a semantic wynik liczy
  wcześniejszych konkurentów.
- **Recommendation:** przekazać do helpera anchor i dokładnie uczestników
  manifestu; niedostępny runtime fact ma dawać jawny partial/insufficient data,
  nie zastąpienie innym produktem.
- **Missing test:** manifest z niepierwszym kompatybilnym konkurentem dowodzi,
  że semantic participant IDs i observations ceny są dokładnie z manifestu.

### P2 — Internal benchmark detail fałszywie zgłasza brak ceny

- **File:** `fieldnote-api/app.py:2919-2932`.
- **Evidence:** endpoint liczy semantic scoring, ale zwraca literalne
  `price_summary={status: no_data, ...}` mimo istniejącej logiki agregacji
  runtime price observations.
- **Impact:** przy dostępnych cenach endpoint podaje fałszywe `median/min/max`
  jako brak danych.
- **Scenario:** trzy Lionelo tej samej konfiguracji mają valid offers, lecz
  `GET /api/internal-benchmarks/{group}` zwraca `median: null`.
- **Recommendation:** agregować ceny dokładnego internal participant scope albo
  pominąć pole, gdy nie można ich wiarygodnie ustalić.
- **Missing test:** internal fixture z cenami sprawdza medianę/min/max oraz
  niezależność utility score od ceny.

### P2 — Brakuje wykonawczych regresji nowych kontraktów API i commitu

- **File:** `tests/test_relative_benchmark_scoring.py`,
  `tests/test_pricing_aggregation.py`, `tests/test_stroller_attribute_audit.py`;
  brak testu dla `fieldnote-api/app.py` i `BenchmarkCommitService._snapshots`.
- **Evidence:** focused 20 testów pokrywa usługowy scoring/schema/ceny, lecz
  żaden nie wywołuje nowych `semantic_benchmark`/`price_summary` endpointów ani
  snapshotu wybierającego `semantic_benchmark`. Nie ma też regresji HTTP 422
  dla 2w1 ↔ 3w1 w competitive manifest API.
- **Impact:** integracja runtime/snapshotu lub odrzucenie konfiguracji może
  zostać usunięte albo zwrócić niezwiązane dane przy zielonej suite Unit 8.
- **Recommendation:** dodać offline API-helper/endpoint i commit snapshot
  fixtures, w tym repeat identycznego stanu bez nowego snapshotu oraz manifest
  2w1/3w1 odrzucony jako 422.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | 2 P1, 1 P2 | 3 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | 1 P1, 2 P2 | 2 P1/P2 skonsolidowane | 0 |
| data_reviewer | 2 P1, 1 P2 | 3 P1/P2 skonsolidowane | 0 |

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused Unit 8 | PASS, 20/20 | scoring, aliases, suspension, config, pricing i corpus 34 |
| `py_compile` touched modules | PASS | API, services, scorer i pipeline |
| `git diff --check 0b985d0^..0b985d0` | PASS | bez błędów whitespace |
| `bash scripts/check_fieldnote.sh` | NIEUKOŃCZONE | istniejący hygiene blokuje się na `git show :<tracked-path>` w tym środowisku |

## Bezpieczeństwo

Security review: PASS. Diff nie wprowadza nowego endpointu, auth/RLS, dostępu
do Storage, sekretów ani wywołań zewnętrznych. Findings dotyczą integralności
danych i zgodności runtime z trwałą relacją benchmarku.

## Decyzja gate

**BLOKUJE** — 2 P1, 2 P2, 0 P3. Unit 8 nie ma PASS; Unit 8.5 i Unit 9 nie
mogą zostać rozpoczęte.

## Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 8` — napraw wyłącznie
zaakceptowane 2 P1 i 2 P2 z tego raportu, potem wykonaj ograniczony re-review
Unit 8. Nie rozpoczynaj Unit 8.5 ani Unit 9.
