# Zadanie 05 — oficjalne strony producentów w tym samym pipeline’ie co Allegro

**Sugerowany model:** GPT-5.6 Terra, reasoning High. Użyj Sol High tylko dla konkretnego blokera architektonicznego.

Rozpocznij wyłącznie po:

`Result: FIELDNOTE_REPAIR_CLOSURE_PASS`

## Cel

Dodać oficjalne strony producentów jako kolejny typ źródła wejściowego, ale **nie tworzyć osobnego równoległego pipeline’u**.

Wspólny przebieg ma pozostać taki:

```text
SourceAdapter
→ source selection
→ fetch orchestration
→ raw snapshot
→ cleaner właściwy dla typu źródła
→ NormalizedDocument
→ wspólna extraction
→ wspólny quality gate
→ EvidenceItem
→ merge per field
→ finalny produkt
→ benchmark/UI
```

Allegro i producent różnią się discovery, fetch metadata i cleanerem. Od `NormalizedDocument` mają używać wspólnych kontraktów i mechanizmów.

## 1. Zakres pierwszego wdrożenia

Obsłuż oficjalne źródła dla:

- Kinderkraft,
- CYBEX.

Kontrolowane modele testowe:

- Kinderkraft NEBO,
- Kinderkraft TIK,
- Kinderkraft TRIG 3,
- Kinderkraft MOOV,
- CYBEX ORFEO.

Nie zakładaj, że każdy model ma dostępną poprawną kartę producenta. Brak oficjalnego źródła nie może blokować analizy marketplace.

Nie dodawaj Amazonu ani drugiego marketplace’u.

## 2. Manufacturer adapter

Rozszerz istniejący `SourceAdapter`, nie kopiuj całego pipeline’u.

Adapter producenta odpowiada za:

- discovery kandydatów,
- walidację oficjalnej domeny,
- klasyfikację strony jako bezpośredniej karty modelu,
- przygotowanie SourceCandidate,
- fetch przez wspólną orkiestrację,
- manufacturer-specific normalize/clean,
- capability flags.

Adapter nie może:

- pisać bezpośrednio `model_state`,
- pisać benchmarku,
- omijać quality gate,
- tworzyć finalnych EvidenceItem poza wspólną warstwą,
- nadpisywać danych Allegro bez porównania per pole.

## 3. Discovery w aplikacji

Research ma pokazywać osobną sekcję `Oficjalne źródła producenta`.

Dla kandydata pokaż:

- URL,
- domenę,
- tytuł,
- brand/model match,
- page type,
- discovery confidence,
- rejection reason,
- status istniejącego snapshotu.

Akceptuj tylko:

- oficjalną domenę producenta,
- bezpośrednią kartę danego modelu lub jednoznaczną oficjalną specyfikację,
- zgodny brand i model/generację.

Odrzucaj:

- strony kategorii,
- wyniki wyszukiwania,
- sklepy partnerskie,
- porównywarki,
- inne modele,
- ogólne strony marki,
- instrukcje bez jednoznacznej identyfikacji produktu.

Użytkownik ma widzieć i zatwierdzić źródło przed analizą. Wybrane źródło zapisuje ProductSourceLink i immutable run context.

## 4. Fetch — ten sam mechanizm co Allegro

Użyj tej samej orkiestracji fetch, timeout/cancel/retry, cache, SourceRecord lifecycle i snapshot storage, które obsługują Allegro.

Jeżeli obecny provider Allegro używa Firecrawl, podłącz strony producentów przez ten sam provider/kontrakt. Nie twórz drugiego niezależnego systemu kolejek i statusów.

Wymagania:

- FIRECRAWL_API_KEY z istniejącego `.env`, bez logowania sekretu,
- raw markdown/HTML/metadata, zależnie od dostępności,
- final URL i redirect chain,
- content hash,
- raw snapshot,
- timeout,
- retry/backoff,
- cancel,
- resume,
- refresh tylko przy zmianie lub jawnym wymuszeniu.

Tryby:

- preview bez fetch,
- fetch wybranego źródła,
- refresh istniejącego źródła,
- local fixture/no-network.

## 5. Manufacturer cleaner

Dodaj cleaner właściwy dla typu źródła `manufacturer`, wywoływany w tej samej fazie clean co cleaner Allegro.

Zachowaj:

- nazwę produktu,
- model/generację/wariant,
- opis modelu,
- tabele parametrów,
- JSON-LD Product,
- wymiary,
- wagę,
- udźwig,
- materiały,
- funkcje techniczne,
- regulacje,
- koła/zawieszenie/składanie,
- kompatybilność,
- normy i bezpieczeństwo,
- elementy standardowego zestawu,
- opcjonalne akcesoria w oddzielnej sekcji,
- linki do oficjalnych PDF/instrukcji.

Usuń lub odseparuj:

- menu i stopkę,
- cookies/newsletter,
- marketing ogólny marki,
- rekomendowane produkty i inne modele,
- dealer locator,
- sklepy i warunki płatności,
- zdublowane bloki mobile/desktop,
- opinie marketingowe,
- treść kategorii.

Zawsze zachowaj:

- raw snapshot,
- clean snapshot,
- cleaner manifest,
- identity result.

Identity result ma blokować dalszą ekstrakcję przy niezgodnym modelu/generacji.

## 6. Deterministyczna normalizacja przed AI

W tej samej warstwie normalizacji co inne źródła najpierw wyciągnij deterministycznie:

- JSON-LD,
- tabele key/value,
- definition lists,
- SKU/EAN/GTIN,
- jawne jednostki,
- wymiary,
- wagę,
- udźwig,
- linki do dokumentów,
- nazwy wariantów.

Każdy fakt kandydacki ma:

- field candidate,
- raw value,
- normalized value,
- exact excerpt,
- source ID,
- section,
- extraction method.

Wynik ma być `NormalizedDocument` zgodny z pipeline’em Allegro.

## 7. OpenAI — wspólna extraction, nie osobny model producenta

Użyj istniejącej warstwy OpenAI extraction wykorzystywanej w research pipeline. Rozszerz prompt/schema o authority i typ dokumentu, ale nie buduj drugiego systemu finalizacji produktu.

OpenAI dostaje:

- cleaned/normalized document,
- deterministyczne fakty,
- kategorię i schema pól,
- source ID,
- identity metadata.

Nie wysyłaj całego surowego HTML.

Model ma:

- mapować tylko dowody obecne w dokumencie,
- podawać exact excerpt,
- nie wymyślać braków,
- rozdzielać model, wariant i konkretny bundle,
- rozdzielać wyposażenie standardowe od opcjonalnego,
- zachować jednostkę i wartość źródłową,
- zgłaszać konflikty.

Każdy wynik przechodzi ten sam EvidenceItem, quality gate i merge per field co Allegro.

## 8. Authority per typ pola

Producent preferowany dla:

- oficjalnych wymiarów,
- wagi,
- udźwigu,
- materiałów,
- funkcji technicznych,
- oficjalnej kompatybilności,
- norm i instrukcji.

Marketplace/sklep preferowany dla:

- aktualnej ceny,
- sprzedawcy,
- dostępności,
- warunków sprzedaży,
- zawartości konkretnej oferty,
- wariantu faktycznie sprzedawanego w danej ofercie.

Nie wybieraj jednego najlepszego źródła dla całego produktu. Wybieraj primary evidence per pole.

Konflikt producent–marketplace zachowaj jawnie. Nie nadpisuj po cichu.

## 9. Content family

Jeżeli aukcja kopiuje opis producenta:

- ta sama content family dla skopiowanych sekcji,
- brak drugiego niezależnego potwierdzenia parametrów technicznych,
- marketplace nadal może być niezależny dla ceny, availability i bundle.

Dedup opieraj na:

- content hash,
- normalized paragraph/section hashes,
- kontrolowanym similarity threshold.

Nie opieraj niezależności wyłącznie na domenie.

## 10. Integracja z run pipeline

W istniejącym pipeline dodaj czytelne etapy producenta, ale nie osobny orchestrator:

- manufacturer discovery,
- selection,
- fetch,
- clean,
- normalize,
- extraction.

Po ekstrakcji wróć do wspólnych etapów:

- quality gate,
- evidence aggregation,
- merge,
- final state,
- metrics,
- benchmark snapshot.

Każdy etap ma:

- progress,
- timeout,
- cancel,
- resume,
- logi,
- manifest status.

Brak lub błąd manufacturer source nie blokuje poprawnej analizy źródeł marketplace, chyba że użytkownik jawnie wymaga tego źródła.

## 11. UI

Research:

- oficjalne źródła osobno,
- status discovery/fetch/clean,
- exact model match,
- możliwość wyboru.

Produkt / źródła:

- badge `Źródło oficjalne`,
- URL,
- data pobrania,
- raw/clean snapshot,
- contribution,
- pola wykorzystujące źródło,
- konflikty z marketplace,
- content family.

Nie pokazuj producenta jako marketplace.

## 12. Kontrola kosztów

Wprowadź:

- cache i content hash,
- skip niezmienionego źródła,
- jedna ekstrakcja AI na unikalną wersję cleaned content family,
- limit liczby stron per produkt,
- limit tokenów/rozmiaru cleaned document,
- brak ponownego AI przy resume zakończonego etapu,
- jawne liczniki Firecrawl i OpenAI per run.

## 13. Testy offline

Offline gate nie może korzystać z sieci ani OpenAI.

Fixtures obejmują:

- poprawną kartę producenta,
- stronę kategorii,
- niewłaściwy model,
- JSON-LD,
- tabelę specyfikacji,
- marketing i rekomendacje,
- opcjonalne akcesoria,
- kopię opisu producenta na marketplace,
- konflikt producent–marketplace,
- brak strony producenta.

Testy:

1. wspólny orchestrator i lifecycle,
2. manufacturer cleaner zachowuje techniczne dane,
3. usuwa inne modele,
4. mismatch blokuje extraction,
5. deterministyczne fakty trafiają do NormalizedDocument,
6. opcjonalne akcesoria nie stają się standardowym zestawem,
7. authority działa per pole,
8. kopia treści nie zwiększa independent confirmation,
9. brak manufacturer nie blokuje marketplace,
10. resume nie powtarza fetch/AI,
11. timeout/cancel działają,
12. zapisy są atomowe,
13. istniejące testy Allegro nie regresują,
14. frontend typecheck/test/build przechodzą.

## 14. Kontrolowany test live

Dodaj jawny skrypt lub tryb wymagający:

- `--allow-network`
- osobno `--allow-openai`

Bez flag nie wolno użyć Firecrawl ani OpenAI.

Po przejściu fixtures wykonaj maksymalnie:

- jeden kontrolowany run Kinderkraft NEBO,
- jeden kontrolowany run CYBEX ORFEO,
- jedna oficjalna karta na model,
- najwyżej jedno wywołanie OpenAI na unikalny cleaned document.

Zapisz liczbę requestów i kosztowe metadane dostępne w odpowiedziach, bez logowania sekretów.

## 15. Status

Nie twórz nowego audytu.

Zaktualizuj tylko:

`docs/audit/IMPLEMENTATION_STATUS.md`

Na końcu wypisz:

```text
manufacturer_adapter_enabled
same_pipeline_as_allegro=true|false
manufacturer_discovery
manufacturer_research_selection
shared_fetch_orchestration
firecrawl_provider_enabled
manufacturer_cleaner
manufacturer_normalized_document
shared_openai_extraction
shared_quality_gate
shared_evidence_merge
manufacturer_authority_per_field
content_family_dedup
manufacturer_ui
fixtures_passed
kinderkraft_live_result
cybex_live_result
firecrawl_requests
openai_requests
backend_tests
frontend_typecheck
frontend_tests
frontend_build
remaining_issues
next_item=MANUFACTURER_PIPELINE_CLOSURE_AUDIT
Result: MANUFACTURER_SAME_PIPELINE_COMPLETE
```

Nie oznaczaj sukcesu, jeśli producent ma osobny finalizujący pipeline albo omija wspólne quality/evidence/merge.
