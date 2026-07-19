# FIELDNOTE — kolejne kroki Codex

## Stan wejściowy

Przyjmij jako zweryfikowane:

- backlog naprawczy P0–P2 jest zamknięty,
- offline test gate przechodzi,
- wspólny pipeline Allegro/producent istnieje,
- kanoniczny live runner to `scripts/check_manufacturer_pipeline_live.py`,
- preflight dla Kinderkraft NEBO przeszedł,
- `FIRECRAWL_API_KEY` i `OPENAI_API_KEY` są obecne,
- nie wykonano jeszcze rzeczywistego live runu,
- następny krok to pojedynczy live run Kinderkraft NEBO.

## Kolejność

Wykonuj dokładnie po kolei:

1. `01_KINDERKRAFT_NEBO_SINGLE_LIVE_RUN.md`
2. `02_CYBEX_ORFEO_SINGLE_LIVE_RUN.md`
3. `03_MANUFACTURER_PRODUCTION_HARDENING.md`
4. `04_MANUFACTURER_FINAL_CLOSURE.md`

## Zasady sterujące

1. Każdy plik jest osobnym etapem.
2. Po sukcesie przejdź automatycznie do kolejnego pliku.
3. Przy błędzie napraw wyłącznie etap, na którym wystąpił błąd.
4. Maksymalnie dwie próby naprawy na etap. Po drugiej nieudanej próbie zatrzymaj się i podaj konkretny blocker.
5. Nie twórz nowych audytów, planów ani alternatywnych pipeline'ów.
6. Nie otwieraj ponownie P0–P2.
7. Nie wykonuj masowych requestów.
8. Nie używaj więcej niż limit zapisany w danym pliku.
9. Nie pokazuj wartości kluczy API.
10. Nie oznaczaj etapu jako PASS, jeżeli testy lub wymagane walidacje nie przeszły.
11. Aktualizuj wyłącznie `docs/audit/IMPLEMENTATION_STATUS.md`, chyba że dany etap jawnie wymaga zmiany kodu lub fixture.
12. Po `04_MANUFACTURER_FINAL_CLOSURE.md` zatrzymaj się. Nie wybieraj samodzielnie drugiego marketplace'u.

## Raportowanie

Po każdym etapie wypisz wyłącznie wymagane pola końcowe z danego pliku oraz `Result`.
