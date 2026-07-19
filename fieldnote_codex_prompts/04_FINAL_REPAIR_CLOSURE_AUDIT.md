# Zadanie 04 — końcowy audyt zamykający naprawy

**Sugerowany model:** GPT-5.6 Terra, reasoning High. Sol High tylko wtedy, gdy wynik audytu jest sprzeczny i wymaga głębokiej analizy.

Rozpocznij dopiero po `Result: P2_COMPLETE`.

To jest audyt weryfikacyjny. Nie dodawaj nowych funkcji, producentów ani marketplace’ów. Nie używaj sieci, Firecrawl, OpenAI ani Playwrighta.

Nie ufaj `IMPLEMENTATION_STATUS.md` bez potwierdzenia w kodzie i testach.

## Cel

Jednoznacznie odpowiedzieć, czy backlog naprawczy po audycie został zamknięty i czy można rozpocząć integrację oficjalnych stron producentów w tym samym pipeline’ie co Allegro.

## 1. Zweryfikuj P0

Sprawdź kod i testy:

- run coordinator,
- immutable run context,
- product lock,
- global aggregation lock,
- timeout,
- cancel,
- recovery,
- atomowe zapisy,
- kanoniczny stan produktu,
- zachowanie wcześniejszego sukcesu po błędzie,
- bezpieczny start/stop bez zabijania obcych procesów.

## 2. Zweryfikuj P1

- deterministyczny quality gate,
- wersjonowana taksonomia,
- benchmark tylko w tej samej kategorii/wersji,
- jeden RunManifest,
- real retry/cancel,
- globalny SourceRecord,
- ProductSourceLink,
- brak globalnego `unassigned` jako substytutu relacji,
- nazwane liczniki źródeł,
- zachowanie legacy i backupów.

## 3. Zweryfikuj P2

- EvidenceItemV1,
- unattributed legacy,
- invalid reference,
- content families,
- niezależne potwierdzenia,
- deterministyczne primary evidence,
- coverage oddzielone od evidence quality,
- nullable metryki produktu nieprzeanalizowanego,
- SourceContribution,
- brak produkcyjnych atrap,
- typed API client,
- wersjonowane kontrakty,
- lazy evidence/snapshots,
- paginacja.

## 4. Zweryfikuj SourceAdapter

- Allegro działa przez wspólny kontrakt,
- fixture adapter działa,
- po `NormalizedDocument` źródła przechodzą wspólne extraction/quality/evidence/merge,
- adapter nie zapisuje bezpośrednio benchmarku ani finalnego model state,
- manufacturer fixture, jeśli istnieje, nie tworzy osobnego równoległego pipeline’u.

## 5. Test gate

Uruchom:

`scripts/check_fieldnote.sh`

Potwierdź, że nie wykonuje sieci ani OpenAI.

## 6. Smoke test lokalny

Uruchom aplikację bez autoreloadu i sprawdź co najmniej:

- `/api/health`
- `/api/products`
- `/api/products/{known_product}`
- `/api/products/{known_product}/sources`
- `/api/products/{known_product}/history`
- `/api/products/{known_product}/benchmark`
- `/api/runs`
- `/api/sources`
- produkt nieprzeanalizowany.

Sprawdź UI:

- Produkty,
- Research,
- Dane produktu,
- Aukcje i źródła,
- Benchmark,
- Historia,
- Uruchomienia.

## 7. Kontrole regresji

- nieudany run nie ukrywa poprzedniego wyniku,
- nieprzeanalizowany produkt nie pokazuje `Braki: 0`,
- coverage nie jest opisywane jako jakość,
- benchmark nie miesza kategorii,
- źródła produktu nie zawierają globalnej kolejki bez linku,
- brak mock retry i fikcyjnych integracji,
- testy nie wykonują requestów zewnętrznych.

Jeżeli w danych istnieje ORFEO z oczekiwanym zestawem, potwierdź:

- selected 10,
- fetched 8,
- failed 2,
- assigned 5,
- fetched-unattached 3.

Nie wymuszaj wyniku, jeśli dane wejściowe są inne; wtedy wyjaśnij rozbieżność.

## 8. Ocena blockerów

Nie traktuj dalszego dzielenia `app.py` i `App.tsx` jako blokera, jeżeli kontrakty i testy są poprawne.

Blockerem są między innymi:

- utrata danych,
- brak atomowych zapisów,
- konkurencyjne runy tego samego produktu,
- niespójne źródła/linki,
- fikcyjny sukces UI,
- nieprzechodzący offline gate,
- adapter omijający wspólny pipeline.

## 9. Wynik

Zaktualizuj wyłącznie:

`docs/audit/IMPLEMENTATION_STATUS.md`

Dodaj sekcję `FINAL REPAIR CLOSURE`:

- verified complete,
- verified partial,
- critical failures,
- non-blocking debt,
- test gate,
- smoke tests,
- manufacturer integration readiness.

Na końcu wypisz:

```text
repair_backlog_closed=true|false
critical_failures
non_blocking_technical_debt
offline_tests_passed=true|false
smoke_tests_passed=true|false
source_adapter_verified=true|false
manufacturer_pipeline_ready=true|false
network_fetches=0
openai_calls=0
next_phase=MANUFACTURER_SOURCES_SAME_PIPELINE
Result: FIELDNOTE_REPAIR_CLOSURE_PASS|FIELDNOTE_REPAIR_CLOSURE_FAIL
```

Przy `FAIL` zatrzymaj się. Nie naprawiaj automatycznie szerokiego zakresu w tym samym zadaniu. Podaj konkretną listę blockerów i testów, które nie przeszły.
