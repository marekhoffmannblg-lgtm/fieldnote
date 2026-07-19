# FIELDNOTE — kolejność pracy w Codexie

Ta paczka zakłada, że audyt został wykonany, ale poprawki i integracja stron producentów **nie zostały jeszcze faktycznie wdrożone**.

Nie wklejaj wszystkich promptów naraz. Każdy prompt uruchamiaj jako osobne zadanie Codexa, w podanej kolejności.

## Kolejność

1. `01_REPAIR_P0_RUNTIME_AND_WRITES.md`
2. `02_REPAIR_P1_DATA_HISTORY_AND_SOURCES.md`
3. `03_REPAIR_P2_PROVENANCE_UI_TESTS_AND_ADAPTER_CONTRACT.md`
4. `04_FINAL_REPAIR_CLOSURE_AUDIT.md`
5. Dopiero po wyniku `FIELDNOTE_REPAIR_CLOSURE_PASS`:
   `05_MANUFACTURER_SOURCES_SAME_PIPELINE.md`
6. Po wdrożeniu producentów:
   `06_MANUFACTURER_PIPELINE_CLOSURE_AUDIT.md`

## Zasada zatrzymania

Po każdym zadaniu:

- sprawdź końcowy `Result`,
- nie przechodź dalej przy `FAIL`,
- przy błędzie daj Codexowi tylko raport z nieudanego etapu i poproś o naprawę wskazanych blockerów,
- nie uruchamiaj ponownie zakończonych migracji bez wyraźnej potrzeby.

## Dobór modelu oszczędnie

Domyślnie używaj:

- **GPT-5.6 Terra, reasoning High** — implementacja P0, P1, P2 i producentów,
- **GPT-5.6 Terra, reasoning Medium lub High** — audyty zamykające,
- **GPT-5.6 Sol, reasoning High** — tylko gdy Terra utknie na problemie architektonicznym albo wprowadza niespójne zmiany,
- **GPT-5.6 Luna** — wyłącznie do małych, jednoznacznych poprawek po audycie, nie do całych etapów.

Nie używaj Ultra/Max dla całej paczki. Najpierw Terra High. Sol uruchamiaj tylko dla jednego konkretnego blokera.

## Ograniczanie kosztu i ryzyka

- P0–P2 oraz pierwszy audyt wykonuj całkowicie offline.
- Nie używaj Firecrawl ani OpenAI przed promptem `05`.
- W integracji producentów najpierw testy fixtures, potem maksymalnie jeden kontrolowany run dla Kinderkraft i jeden dla CYBEX.
- Nie dodawaj Amazonu, drugiego marketplace’u, automatycznego odświeżania w tle ani trybu wieloużytkownikowego w tej paczce.
- Aktualizuj jeden plik statusu: `docs/audit/IMPLEMENTATION_STATUS.md`.
- Raport końcowy zadania ma być krótki. Kod i testy są ważniejsze niż kolejne dokumenty audytowe.

## Co oznacza koniec paczki

Po pozytywnym wyniku promptu `06` aplikacja powinna mieć:

- zamknięty backlog naprawczy P0–P2,
- wspólny pipeline dla Allegro i źródeł producentów,
- osobne adaptery/cleanery wejściowe, ale wspólne provenance, quality gate, evidence, merge i UI,
- działające źródła oficjalne co najmniej dla kontrolowanych przypadków Kinderkraft i CYBEX,
- pełną bramkę testową offline,
- kontrolowany test live z ograniczeniem liczby requestów i wywołań modelu.
