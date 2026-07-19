# Zadanie 06 — audyt zamykający integrację producentów

**Sugerowany model:** GPT-5.6 Terra, reasoning High.

Rozpocznij dopiero po:

`Result: MANUFACTURER_SAME_PIPELINE_COMPLETE`

To jest ostatni audyt tej paczki. Nie dodawaj drugiego marketplace’u ani Amazonu.

## Tryb

Najpierw wykonaj pełną weryfikację offline.

Kontrolowany live test jest dozwolony tylko z jawnymi flagami i budżetem:

- maksymalnie 2 requesty Firecrawl łącznie,
- maksymalnie 2 wywołania OpenAI łącznie,
- jeden produkt Kinderkraft,
- jeden produkt CYBEX.

Nie wykonuj masowego refreshu.

## Cel

Potwierdzić, że źródła producentów rzeczywiście działają w tej samej architekturze i pipeline’ie co Allegro oraz że aplikacja jest gotowa na kolejną kategorię źródła bez nowej rundy napraw fundamentów.

## 1. Architektura

Zweryfikuj w kodzie:

- wspólny SourceAdapter contract,
- wspólny run coordinator,
- wspólny fetch lifecycle,
- wspólny SourceRecord/ProductSourceLink,
- manufacturer-specific cleaner/normalizer tylko przed NormalizedDocument,
- wspólna extraction,
- wspólny quality gate,
- wspólny EvidenceItem,
- wspólny merge per field,
- wspólne metryki i UI.

FAIL, jeżeli producent ma osobny zapis finalnego produktu lub omija którykolwiek wspólny etap.

## 2. Discovery i selection

Sprawdź:

- tylko oficjalne domeny,
- bezpośrednia karta modelu,
- identity match,
- rejection reasons,
- preview w Research,
- jawny wybór źródła,
- zapis source ID i ProductSourceLink w run context.

## 3. Fetch i snapshoty

- ten sam timeout/cancel/retry/recovery,
- raw snapshot,
- clean snapshot,
- content hash,
- skip unchanged,
- resume,
- brak logowania sekretów,
- brak duplikowania source ID dla snapshotu.

## 4. Cleaner i NormalizedDocument

Na fixtures potwierdź:

- zachowanie tabel/JSON-LD/specyfikacji,
- usunięcie innych modeli i rekomendacji,
- rozdzielenie standardowego zestawu od opcji,
- blokadę mismatched model,
- dokładne excerpts,
- deterministyczne facts przed AI.

## 5. Extraction, quality i merge

- OpenAI otrzymuje cleaned/normalized document, nie surowy pełny HTML,
- brak halucynowanych pól bez excerpt,
- ten sam EvidenceItem i quality gate,
- primary evidence per pole,
- manufacturer authority tylko dla właściwych pól,
- marketplace zachowuje authority dla ceny/sprzedawcy/availability/bundle,
- jawne konflikty,
- kopie treści nie zwiększają niezależnych potwierdzeń.

## 6. Koszty

Sprawdź:

- cache,
- content hashes,
- jeden AI extraction per unikalna wersja cleaned content family,
- limity stron i rozmiaru,
- brak powtórzeń przy resume,
- liczniki requestów per run.

## 7. Testy

Uruchom pełny:

`scripts/check_fieldnote.sh`

Musi pozostać offline.

Następnie uruchom kontrolowany live test tylko wtedy, gdy wymagane klucze i flagi są dostępne. Brak klucza live nie może oblać offline readiness, ale ma zostać oznaczony jako `live_not_executed`, nie `passed`.

## 8. Smoke UI/API

Sprawdź:

- Research preview oficjalnego źródła,
- run ze źródłem producenta,
- źródła produktu,
- badge oficjalny,
- raw/clean snapshot,
- contribution,
- konflikty,
- benchmark bez regresji,
- produkt bez manufacturer source nadal działa.

## 9. Wynik i dalszy krok

Zaktualizuj tylko:

`docs/audit/IMPLEMENTATION_STATUS.md`

Dodaj sekcję `MANUFACTURER PIPELINE CLOSURE`:

- verified architecture,
- offline results,
- live results,
- costs/request counts,
- supported domains,
- tested models,
- non-blocking debt,
- readiness for second marketplace.

Na końcu wypisz:

```text
manufacturer_same_pipeline_verified=true|false
offline_gate_passed=true|false
kinderkraft_fixture_passed=true|false
cybex_fixture_passed=true|false
kinderkraft_live=passed|failed|not_executed
cybex_live=passed|failed|not_executed
manufacturer_authority_verified=true|false
content_family_dedup_verified=true|false
shared_quality_gate_verified=true|false
shared_merge_verified=true|false
firecrawl_requests
openai_requests
critical_failures
non_blocking_debt
manufacturer_sources_ready=true|false
next_marketplace_ready=true|false
amazon_ready=false
next_phase=SECOND_MARKETPLACE_SELECTION
Result: MANUFACTURER_PIPELINE_CLOSURE_PASS|MANUFACTURER_PIPELINE_CLOSURE_FAIL
```

Po `PASS` nie twórz kolejnego ogólnego audytu naprawczego. Następnym zadaniem produktowym jest wybór i implementacja jednego konkretnego drugiego marketplace’u przez istniejący SourceAdapter.
