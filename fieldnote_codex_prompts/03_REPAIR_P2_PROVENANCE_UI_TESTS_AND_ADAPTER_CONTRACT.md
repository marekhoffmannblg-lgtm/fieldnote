# Zadanie 03 — P2: provenance, metryki, UI, testy i wspólny kontrakt adapterów

**Sugerowany model:** GPT-5.6 Terra, reasoning High.

Rozpocznij dopiero po `Result: P1_COMPLETE`.

Pracuj offline. Nie używaj Firecrawl, OpenAI ani zewnętrznej sieci. Nie wdrażaj jeszcze produkcyjnego pobierania stron producentów.

## Cel

Domknąć backlog naprawczy lokalnego MVP i przygotować wspólny pipeline, do którego później zostaną podłączone strony producentów.

## 1. EvidenceItemV1

Wprowadź wersjonowany kontrakt:

```json
{
  "schema_version": "1",
  "evidence_id": "",
  "product_slug": "",
  "field_name": "",
  "normalized_field_name": "",
  "value": null,
  "normalized_value": null,
  "source_id": null,
  "product_source_link_id": null,
  "excerpt": "",
  "evidence_status": "valid|weak|conflicting|rejected|unattributed_legacy|invalid_reference",
  "validation_status": "",
  "confidence": "high|medium|low|unknown",
  "source_authority": "manufacturer|marketplace|other|unknown",
  "content_family_id": null,
  "confirmation_weight": 0,
  "is_independent_confirmation": false,
  "created_at": "",
  "updated_at": ""
}
```

Zasady:

- stabilne `evidence_id`,
- normalizacja historycznych form string/dict/list/null,
- brak `source_id` → `unattributed_legacy`, bez zgadywania,
- nieistniejący source/link → `invalid_reference`,
- rejected evidence pozostaje w historii,
- każdy zaakceptowany evidence ma dokładny excerpt,
- evidence bez poprawnego SourceRecord i ProductSourceLink nie zwiększa jakości.

Dodaj migrację offline z `--dry-run`, `--apply`, `--resume`, `--product-slug`, `--all` oraz backupem.

## 2. Content families i niezależne potwierdzenia

Wprowadź wspólną logikę niezależności:

- ten sam content hash → jedna rodzina,
- znormalizowane, niemal identyczne sekcje → jedna rodzina,
- kopia opisu producenta na marketplace nie zwiększa niezależnych potwierdzeń technicznych,
- różne źródła handlowe mogą pozostać niezależne dla ceny, dostępności i konkretnego bundle.

Dla każdego pola wylicz:

- primary evidence,
- confirming evidence,
- conflicting evidence,
- rejected evidence,
- total sources count,
- independent confirmations count,
- content families count.

Primary evidence wybieraj deterministycznie:

1. valid przed weak,
2. authority właściwe dla typu pola,
3. jakość źródła,
4. czas pobrania,
5. stabilny source ID jako tie-breaker.

Kolejność tablicy nie może wpływać na wynik.

## 3. Metryki produktu

Wprowadź `ProductMetricsV1` i rozdziel:

- coverage,
- evidence quality,
- source confidence.

Produkt nieprzeanalizowany:

- `coverage_percent=null`,
- `evidence_quality_percent=null`,
- `fields_missing=null`,
- `analysis_complete=false`.

UI nie może pokazywać `0%` ani `Braki: 0`, gdy analiza nie została wykonana.

Unattributed legacy i invalid reference nie zwiększają evidence quality.

## 4. SourceContributionV1

Dla każdego ProductSourceLink wylicz wkład:

- new fields,
- confirmed fields,
- conflicting fields,
- rejected evidence,
- final fields used,
- used fields count,
- independent confirmation count,
- content family count,
- has contribution.

`used_in_final_product=false` nie oznacza rejected.

Źródło bez wkładu ma mieć czytelny komunikat, nie pusty panel.

## 5. UI

### Lista produktów

Pokaż:

- status,
- coverage,
- evidence quality,
- liczbę użytych źródeł,
- braki lub `Nie przeanalizowano`,
- ostrzeżenie po nieudanym odświeżeniu przy zachowaniu wcześniejszego wyniku.

### Dane produktu

Dla każdego pola:

- wartość,
- validation status,
- confidence,
- primary source,
- wszystkie źródła,
- independent confirmations,
- content families,
- konflikty,
- legacy evidence.

Filtry:

- wszystkie,
- valid,
- weak,
- conflicting,
- missing,
- legacy.

### Aukcje i źródła

- tylko ProductSourceLink danego produktu,
- lifecycle źródła,
- contribution,
- raw/clean snapshot,
- failed i fetched-unattached,
- czytelny brak wkładu.

### Benchmark

- nie miesza kategorii,
- odróżnia brak danych, słaby evidence, konflikt i poprawną wartość,
- nie jest kopią widoku danych produktu.

### Historia

- jeden RunManifest,
- brak alternatywnego mock modelu.

## 6. Usuń atrapy produkcyjne

Znajdź i usuń, podłącz albo oznacz `Demo`:

- fikcyjne integracje i klucze,
- hardcoded użytkownika/workspace,
- timerowe retry/save,
- martwe przyciski,
- fikcyjne statusy i statystyki,
- nieistniejący kanał wsparcia.

Żaden przycisk nie może symulować sukcesu bez backendu.

Napraw favicon, loading/error/empty states i surowe techniczne statusy widoczne użytkownikowi.

## 7. Kontrakty API i typed client

Wprowadź wspólne wersjonowane modele backend/frontend co najmniej dla:

- Product,
- ProductMetrics,
- EvidenceItem,
- SourceRecord,
- ProductSourceLink,
- SourceContribution,
- RunManifest,
- Benchmark.

Frontend korzysta z jednego typed API client. Nie utrzymuj wielu sprzecznych typów tego samego obiektu.

Dodaj paginację co najmniej dla:

- produktów,
- runów,
- globalnych źródeł,
- evidence,
- źródeł produktu.

Pełne evidence i snapshoty pobieraj lazy.

## 8. Ewolucyjna modularizacja

Nie przepisuj aplikacji od zera.

Wydziel tylko moduły potrzebne do tego etapu:

Backend:

- models,
- repositories,
- services,
- routers.

Frontend:

- api,
- contracts,
- routes,
- pages/components/hooks.

Po każdej małej zmianie uruchamiaj testy. Dalsza modularizacja może pozostać długiem nieblokującym.

## 9. Fixture E2E

Rozbuduj offline gate o fixture E2E obejmujące:

1. research z lokalnego listingu,
2. wybór źródeł,
3. analizę lokalnych fixture bez OpenAI/Firecrawl,
4. finalny produkt,
5. źródła produktu,
6. benchmark,
7. historię,
8. failed run,
9. retry,
10. cancel,
11. restart/recovery,
12. produkt nieprzeanalizowany,
13. wcześniejszy sukces + późniejszy błąd,
14. równoległe runy.

## 10. Wspólny SourceAdapter

Wprowadź jeden kontrakt wejściowy dla źródeł:

- `discover(query, context)`
- `fetch(source, context)`
- `normalize(raw_source)`
- `classify(normalized_source, product_context)`
- `enrich(normalized_source)`
- `healthcheck()`
- `capabilities()`

Wspólne modele:

- SourceCandidate,
- FetchResult,
- NormalizedDocument,
- EvidenceCandidate.

Zasady:

- adapter nie zapisuje bezpośrednio benchmarku ani finalnego model state,
- po `NormalizedDocument` wszystkie źródła korzystają ze wspólnej ekstrakcji, quality gate, evidence i merge,
- istniejącą logikę Allegro opakuj adapterem bez zmiany zachowania,
- dodaj adapter fixtures,
- można dodać manufacturer fixture na istniejącym lokalnym snapshotcie, ale bez live discovery/fetch,
- authority i content family są wspólne, nie kopiowane w każdym adapterze,
- dodaj retry/rate-limit interface i capability flags.

## 11. Gate

`scripts/check_fieldnote.sh` ma jawnie uruchamiać:

- syntax/import checks,
- backend unit/integration,
- P0/P1/P2,
- source lifecycle,
- provenance,
- fixture E2E,
- frontend typecheck,
- frontend tests,
- frontend build.

Zero requestów zewnętrznych.

## 12. Status

Zaktualizuj tylko:

`docs/audit/IMPLEMENTATION_STATUS.md`

Na końcu wypisz:

```text
p2_evidence_v1
p2_provenance_migrated
unattributed_legacy_count
invalid_reference_count
content_families_count
independent_confirmation_logic
product_metrics_v1
coverage_quality_separated
source_contribution_v1
unanalysed_products_fixed
mock_ui_removed_or_marked
api_contracts_versioned
typed_api_client
pagination
fixture_e2e
offline_test_gate
source_adapter_contract
allegro_adapter
manufacturer_fixture_adapter
backend_tests
frontend_typecheck
frontend_tests
frontend_build
network_fetches=0
openai_calls=0
next_item=FINAL_REPAIR_CLOSURE_AUDIT
Result: P2_COMPLETE
```

Nie oznaczaj sukcesu przy nieprzechodzącym gate, niezgodnych metrykach albo mockach sugerujących działającą funkcję.
