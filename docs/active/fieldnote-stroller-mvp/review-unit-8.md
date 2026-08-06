# Review — Unit 8: Audyt atrybutów i względny scoring wózków

- **Data:** 2026-08-06
- **Zakres diffu:** ograniczony re-review `f5fca8c^..f5fca8c`
- **Tryb:** re-review
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, data_reviewer`
- **Gate:** `BLOKUJE`

## Kryteria akceptacji unitu

- Jednostką porównania, wyniku i trwałego snapshotu jest `model + konfiguracja`.
- Cena pozostaje osobnym wymiarem i używa dokładnego scope benchmarku.
- Competitive benchmark używa zatwierdzonego manifestu; internal wymaga co
  najmniej trzech Lionelo w tej samej konfiguracji.
- Scoring, ceny i durable history są deterministyczne i idempotentne.

## Zgodność z planem i zakresem

Sprawdzono wyłącznie remediation ostatnich 2 P1 i 2 P2 Unit 8 z commitu
`f5fca8c`: konfigurację scoped commitu/snapshotu, manifest participant scope,
internal price summary oraz regresje. Nie sprawdzano ani nie rozpoczynano
Unit 8.5 lub Unit 9; nie modyfikowano kodu podczas review.

## Skonsolidowane findings

### P1 — Durable snapshot nadal nie ma konfiguracyjnej tożsamości

- **File:** `scripts/run_model_research_pipeline.py:153-205`,
  `fieldnote-api/services/benchmark_commit_service.py:123-135` oraz
  `supabase/migrations/202607290001_incremental_benchmark_commit.sql:92-100`.
- **Evidence:** konfiguracja targetu i kandydatów jest odczytywana tylko z
  `product_scope` albo legacy `group.json`/`model_state.json`; normalny job
  jej nie propaguje, a aktualne group files jej nie zawierają. Ponadto durable
  benchmark snapshot nadal ma `scope_id=benchmark_group`, podczas gdy RPC
  wybiera poprzedni snapshot po tej parze scope type/id.
- **Impact:** 2w1 i 3w1 mogą wejść do jednego scorer scope, a naprzemienne
  refreshy identycznych danych tworzą fałszywe semantic transitions.
- **Scenario:** commit 2w1, potem 3w1, potem niezmieniony 2w1: trzeci commit
  porównuje hash z 3w1, zamiast z ostatnim 2w1.
- **Recommendation:** propagować kanoniczną konfigurację z katalogu przez
  job/run context, używać katalogowego fallbacku dla legacy group files oraz
  partycjonować durable scope/RPC per konfiguracja.
- **Missing test:** realny `JobService → PipelineService → scoped_commit` z
  config-less group files i 2w1/3w1 oraz opt-in RPC z naprzemiennymi commitami.

### P1 — Competitive manifest z anchorem Lionelo nadal liczy internal cohort

- **File:** `fieldnote-api/app.py:1692-1768`.
- **Evidence:** `competitive_benchmark_detail()` przekazuje manifest IDs, ale
  `runtime_semantic_benchmark()` wybiera `build_internal_benchmark()` wyłącznie
  na podstawie marki anchora Lionelo. Ignoruje więc manifestowych konkurentów
  dla score, a `selected_ids` zbiera wszystkie Lionelo tej konfiguracji dla cen.
- **Impact:** response benchmarku „Lionelo vs konkurent” może prezentować
  internal score i Lionelo-only price evidence, nie wynik zatwierdzonego
  manifestu.
- **Scenario:** manifest `Lionelo A` vs `Bugaboo B` zwraca ranking Lionelo A
  względem innych Lionelo i ceny bez Bugaboo B.
- **Recommendation:** przekazać jawny tryb competitive/manifest scope;
  competitive detail ma używać `build_competitive_benchmark(anchor, manifest
  participants)` oraz cen dokładnie `{anchor, participants}`.
- **Missing test:** realna fixture anchor Lionelo, dodatkowego Lionelo i
  manifestowego konkurenta, asercja semantic IDs i observations ceny.

### P2 — Internal price summary nie jest zasilane realnymi cenami pipeline

- **File:** `fieldnote-api/app.py:1767-1775` i
  `scripts/build_model_groups.py:295-312`.
- **Evidence:** agregator czyta cenę wyłącznie z `group.json`, lecz scoped
  projection model groups nie zapisuje `price`; sprawdzone group files nie
  zawierają tego pola. Mock w nowym teście omija tę ścieżkę.
- **Impact:** endpoint nadal zwraca `no_data`, gdy ceny istnieją w listing/source
  artifacts.
- **Recommendation:** zachować walidowane price/seller/availability/timestamp
  w projection albo agregować z kanonicznych rekordów source/offer.
- **Missing test:** real-shaped fixture trzech internal produktów z cenami,
  deduplikacją sprzedawcy i medianą/min/max.

### P2 — Zmieniony moduł testów API kończy się błędem i nie testuje realnego scope

- **File:** `tests/test_competitive_benchmarks.py:95-119`.
- **Evidence:** `test_internal_detail_exposes_runtime_price_summary()` odwołuje
  się do niezdefiniowanego `manifest`; test wykonawczy kończy się `NameError`.
  Równocześnie nowe testy mockują `runtime_semantic_benchmark`, więc nie
  sprawdzają faktycznego manifest scope ani cen.
- **Impact:** zmieniony moduł API jest czerwony, a istotne regresje mogą przejść
  niezauważone.
- **Recommendation:** przywrócić asercje lifecycle do create/read/list testu i
  dodać lokalne, niemockowane fixtures dla competitive/internal oraz HTTP 422
  2w1 ↔ 3w1.
- **Missing test:** samodzielne uruchomienie zmienionego modułu i przypadki
  manifest competitor scope, internal price oraz konfiguracyjnej odmowy 422.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | 2 P1, 1 P2 | 3 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | 1 P1, 3 P2 | 2 P1/P2 skonsolidowane | 0 |
| data_reviewer | 1 P1, 1 P2 | 2 P1/P2 skonsolidowane | 0 |

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Pipeline/snapshot focused suite | PASS, 10/10 | `tests.test_incremental_pipeline`, `tests.test_semantic_snapshots` |
| Zmienione testy API | FAIL, 2 PASS + 1 ERROR | `NameError: manifest is not defined` w internal price teście |
| `py_compile` changed files | PASS | pipeline, app, service i testy |
| `git diff --check f5fca8c^..f5fca8c` | PASS | brak błędów whitespace |
| `bash scripts/check_fieldnote.sh` | NIEUKOŃCZONE | istniejący hygiene blokuje się na `git show :<tracked-path>` |

## Bezpieczeństwo

Security review: PASS. Diff nie zmienia auth, RLS, Storage, sekretów,
zewnętrznych providerów ani granicy uprawnień endpointów.

## Odchylenia od planu

Brak rozszerzenia scope. Unit 8.5 i Unit 9 nie zostały rozpoczęte.

## Kontrole operatora

Brak ręcznych kontroli oznaczonych jako wykonane.

## Decyzja gate

**BLOKUJE** — 2 P1, 2 P2, 0 P3. Unit 8 nie ma PASS.

## Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 8` — napraw wyłącznie
zaakceptowane 2 P1 i 2 P2 z tego raportu; następnie wykonaj ograniczony
re-review Unit 8. Nie rozpoczynaj Unit 8.5 ani Unit 9.
