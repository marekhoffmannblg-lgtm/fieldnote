# Audyt MVP aplikacji benchmarkowej

Data audytu: 2026-07-13

## Zakres i metoda

Audyt objął `app.py`, skrypt uruchamiający research, pipeline Firecrawl i OpenAI, grupowanie modeli, budowę benchmarku, coverage, dane NEBO/TRIG 3/TIK, obsługę błędów, onboarding, README oraz dokumentację architektury.

Sprawdzono statycznie składnię wszystkich skryptów Python: `syntax_errors=0`. Uruchomiono aplikację lokalnie i przetestowano ścieżki, które nie wymagają kluczy ani zapisu do danych. Nie uruchomiono pełnego researchu ze skutecznym Firecrawl/OpenAI, ponieważ wymagałby kluczy API i zmieniłby audytowaną kolejkę oraz artefakty.

## Stan danych w chwili audytu

| Model | Źródła | Coverage | Potwierdzone | X | Wniosek |
|---|---:|---:|---:|---:|---|
| Kinderkraft NEBO | 2 | 52,38% | 11 | 9 | konflikty / braki, research rekomendowany |
| Kinderkraft TIK | 4 | 57,14% | 12 | 9 | research rekomendowany |
| Kinderkraft TRIG 3 | 5 | 61,90% | 13 | 8 | research rekomendowany |

Kolejka Firecrawl zawiera 232 rekordy: 32 `fetched`, 199 `pending`, 1 `error` po timeoutcie. Rejestr źródeł zawiera 32 pobrane rekordy i 13 grup modeli, ale tylko trzy grupy mają `model_state.json`, coverage i są widoczne w aplikacji. To rozróżnienie jest ważne: dashboard nie pokazuje pełnego katalogu źródeł, tylko modele po zakończonym etapie stanu/coverage.

## Przebieg ścieżek użytkownika

| Ścieżka | Wynik | Uwagi |
|---|---|---|
| Otwarcie aplikacji | OK | Aplikacja lokalna ładuje się bez błędów konsoli. |
| Samouczek | OK | Cztery kroki są widoczne; pominięcie działa w `session_state`. |
| Lista modeli | OK | Widoczne NEBO, TIK i TRIG 3; sortowanie jest dostępne. |
| Szczegóły modelu | OK | NEBO pokazuje coverage, pola, statusy, evidence i powody researchu. |
| Porównanie modeli | OK | Domyślnie porównuje trzy modele; limit 2–5 jest dostępny. |
| Formularz researchu | Częściowo OK | Formularz, logika argumentów i brak wycieku kluczy są poprawne. Sukces E2E nie był wykonywany. |
| Brak klucza Firecrawl | OK | UI zatrzymuje proces przed uruchomieniem dla nowego modelu i wyświetla czytelny błąd. |
| Brak klucza OpenAI | OK | Przy zapisanym listingu i wyłączonym `Skip AI` UI zatrzymuje proces przed uruchomieniem. |
| Brak wyników | Tylko statycznie | Kod ma komunikaty pustego stanu, ale brak bezpiecznej fixture/flag do uruchomienia tego scenariusza bez zmiany danych. |
| Błąd pipeline | Częściowo OK | Runner zwraca `pipeline_status=failed` dla nieobsługiwanego marketplace. Nie sprawdzono prezentacji błędu z prawdziwego etapu Firecrawl/OpenAI bez modyfikacji danych. |
| Odświeżenie po sukcesie | Tylko statycznie | Kod czyści cache i wykonuje `st.rerun()` po `pipeline_status=success`, ale nie zweryfikowano tego na prawdziwym sukcesie. |

## P0 — blokuje używanie aplikacji

### P0-1. Pipeline może zgłosić sukces po nieudanym pobraniu kart ofert

Opis: `fetch_firecrawl_offer_pages.py` zapisuje błąd każdej oferty do kolejki i kończy się kodem 0, o ile nie wystąpi błąd globalny. Runner traktuje wtedy etap 3 jako udany i przechodzi do cleanera, registry, grup oraz coverage. W efekcie research może zakończyć się `pipeline_status=success` mimo że nowe oferty nie zostały pobrane. Obecnie w kolejce istnieje realny przykład takiego problemu: `offer-0230` ma status `error` po timeoutcie.

Gdzie występuje: [fetch_firecrawl_offer_pages.py](scripts/fetch_firecrawl_offer_pages.py:124), [run_model_research_pipeline.py](scripts/run_model_research_pipeline.py:174).

Wpływ na użytkownika: użytkownik otrzymuje zielony wynik researchu, ale coverage nie wzrasta albo opiera się wyłącznie na starych źródłach. To podważa zaufanie do całego benchmarku.

Proponowane rozwiązanie: fetcher powinien zwracać oddzielne liczniki `fetched`, `failed`, `skipped`; runner powinien przerwać proces lub oznaczyć go jako częściowy błąd, gdy nowe targetowane oferty zakończyły się `error`. Podsumowanie UI powinno prezentować te trzy liczby.

Trudność: średnia.

## P1 — konieczne przed pokazaniem użytkownikom

### P1-1. Znaczenie opcji `Apply` jest mylące, a pipeline mimo braku Apply przebudowuje globalne artefakty

Opis: bez `--apply` runner nie dodaje nowych ofert do kolejki, ale nadal po etapie wyszukania uruchamia cleaner, source registry, grupowanie, benchmark i coverage dla całego zestawu danych. Domyślne ustawienia UI to `Apply=false`, `Resume=true`, `Skip AI=true`; użytkownik może oczekiwać pełnego researchu, a otrzymać wyłącznie odświeżenie istniejących plików.

Gdzie występuje: [app.py](app.py:487), [run_model_research_pipeline.py](scripts/run_model_research_pipeline.py:165).

Wpływ na użytkownika: niejasne skutki przycisku „Uruchom pipeline”, nieoczekiwane modyfikacje raportów oraz ryzyko błędnej interpretacji udanego procesu jako pozyskania nowych danych.

Proponowane rozwiązanie: rozdzielić dwa wyraźne tryby: „Podgląd wyszukiwania, bez zmian danych” oraz „Zastosuj wyniki i pobierz oferty”. Przy braku `Apply` nie uruchamiać etapów 4–9. Dodać ekran potwierdzenia opisujący, które pliki i rekordy zostaną zmienione.

Trudność: średnia.

### P1-2. Błędy kolejki nie mają retry ani ścieżki odzyskania w UI

Opis: rekord po timeoutcie otrzymuje trwały status `error`. Fetcher bierze wyłącznie `pending`, a UI nie pokazuje błędów kolejki ani nie pozwala bezpiecznie ponowić konkretnej oferty.

Gdzie występuje: [fetch_firecrawl_offer_pages.py](scripts/fetch_firecrawl_offer_pages.py:124), [app.py](app.py:471).

Wpływ na użytkownika: część modeli może nigdy nie uzyskać dodatkowych danych, bez widocznej informacji dlaczego.

Proponowane rozwiązanie: dodać `retry_count`, `last_error_at` i komendę/akcję „Ponów błędne pobrania” z limitem prób oraz backoffem. Pokazać błędy i liczbę pending/error w widoku researchu.

Trudność: średnia.

### P1-3. Dashboard ukrywa 10 istniejących grup modeli bez jasnego statusu

Opis: istnieje 13 folderów `output/model_groups`, lecz `load_dashboard_data()` buduje listę wyłącznie z `model_coverage.csv`, która zawiera trzy wiersze. Modele bez `model_state.json` i coverage znikają z katalogu zamiast pojawić się jako „czeka na analizę”.

Gdzie występuje: [app.py](app.py:96).

Wpływ na użytkownika: ekran „Modele w benchmarku: 3” sugeruje pełny katalog, choć źródła zawierają co najmniej 13 modeli. Użytkownik nie widzi kolejki prac i nie może wybrać modelu do researchu z kompletnej listy.

Proponowane rozwiązanie: scalać `group.json`, `model_state.json` i coverage w jeden katalog. Dla grup bez state pokazywać status „niezainicjalizowany” oraz akcję researchu; rozróżnić „modele w katalogu” od „modele z benchmarkiem”.

Trudność: średnia.

### P1-4. Brak bezpiecznego testowego trybu E2E dla stanu pustego, błędu i sukcesu

Opis: scenariusze „brak wyników”, „prawdziwy błąd etapu” oraz „odświeżenie po sukcesie” wymagają zmian w globalnych plikach albo realnych kluczy. Aktualny audit może je ocenić tylko statycznie.

Gdzie występuje: [app.py](app.py:96), [run_model_research_pipeline.py](scripts/run_model_research_pipeline.py:146).

Wpływ na użytkownika: regresje w najważniejszych ścieżkach operacyjnych mogą zostać wykryte dopiero na danych produkcyjnych.

Proponowane rozwiązanie: dodać wyłącznie do środowiska testowego konfigurowalne katalogi danych i fixture runnera zwracającego sukces/błąd/pusty wynik. Nie musi to być nowy check; wystarczy izolowany tryb demonstracyjny.

Trudność: średnia.

### P1-5. Dokumentacja opisuje poprzedni produkt, nie aktualny dashboard i pipeline

Opis: `docs/APP_SPEC.md` mówi, że `app.py` czyta `market_offers.csv`, że Firecrawl API i benchmark extractor są przyszłe oraz że nie należy używać AI. Aktualny kod czyta `model_coverage.csv` i `model_benchmark.csv`, ma fetcher Firecrawl, cleaner i dwa etapy AI.

Gdzie występuje: [APP_SPEC.md](docs/APP_SPEC.md:32), [README.md](README.md:101).

Wpływ na użytkownika: nie można wiarygodnie uruchomić ani zrozumieć systemu wyłącznie na podstawie dokumentacji; onboarding techniczny prowadzi do starego workflow.

Proponowane rozwiązanie: zaktualizować jedną kanoniczną instrukcję „od listingów do model coverage” oraz usunąć albo oznaczyć jako legacy opisy market browsera.

Trudność: mała.

## P2 — poprawa jakości

### P2-1. Dwa równoległe pipeline’y AI i benchmarku są niejednoznaczne

Opis: istnieją `extract_product_facts_with_ai.py` + `build_benchmark_ai_validated.py` oraz aktywna kaskada `extract_model_facts_cascade.py` + `build_model_benchmark.py`. Runner używa tylko kaskady, a oba zestawy artefaktów pozostają w repozytorium.

Gdzie występuje: [extract_product_facts_with_ai.py](scripts/extract_product_facts_with_ai.py:82), [extract_model_facts_cascade.py](scripts/extract_model_facts_cascade.py:198), [run_model_research_pipeline.py](scripts/run_model_research_pipeline.py:185).

Wpływ na użytkownika: trudno ustalić, który CSV jest właściwym benchmarkiem i który etap ma być uruchamiany po pobraniu ofert.

Proponowane rozwiązanie: oznaczyć jeden flow jako legacy albo opisać ich precyzyjny podział odpowiedzialności; w UI i README wskazywać tylko kanoniczny output.

Trudność: mała.

### P2-2. Widok szczegółów nie pokazuje pełnej provenance dla konfliktów

Opis: `field_rows()` wybiera pierwsze `source_id` i pierwszy URL, natomiast evidence z kilku źródeł scala w jeden tekst. Dla pola konfliktowego użytkownik nie widzi czytelnego porównania „wartość → źródło”.

Gdzie występuje: [app.py](app.py:333).

Wpływ na użytkownika: ręczna weryfikacja konfliktów jest utrudniona, mimo że UI deklaruje pracę z evidence.

Proponowane rozwiązanie: dodać expander „Źródła pola” z osobnym wierszem na każdy evidence item oraz widocznym source ID, marketplace i linkiem.

Trudność: mała.

### P2-3. Interfejs pozostawia techniczne, anglojęzyczne kontrolki tabel Streamlit

Opis: przy tabelach widoczne są standardowe akcje „Show/hide columns”, „Download as CSV”, „Search” i „Fullscreen”, podczas gdy reszta interfejsu jest po polsku i ma nietechniczny charakter.

Gdzie występuje: [app.py](app.py:323), [app.py](app.py:389), [app.py](app.py:435).

Wpływ na użytkownika: interfejs wygląda mniej spójnie i częściowo przeczy założeniu lokalnego dashboardu dla użytkownika nietechnicznego.

Proponowane rozwiązanie: ograniczyć standardowe kontrolki albo zastąpić tabelę własnym, polskojęzycznym komponentem/listą kart w MVP.

Trudność: średnia.

### P2-4. Brak trwałej historii uruchomień i widoczności stanu pipeline’u

Opis: log oraz wynik procesu są przechowywane tylko w `st.session_state`. Po odświeżeniu strony użytkownik traci kontekst ostatniego researchu; brak też widoku liczby `pending`, `fetched` i `error`.

Gdzie występuje: [app.py](app.py:471), [app.py](app.py:522).

Wpływ na użytkownika: trudno ocenić, co zostało wykonane i które rekordy wymagają działania.

Proponowane rozwiązanie: zapisywać krótki, zanonimizowany manifest uruchomienia w `output/research_runs/` oraz pokazać go w UI. Nie przechowywać kluczy ani promptów.

Trudność: średnia.

### P2-5. Pipeline przetwarza globalnie wszystkie pobrane karty zamiast tylko nowych ofert modelu

Opis: stage 4 cleaner bez limitu czyta wszystkie rekordy `fetched`; source registry i group builder również przebudowują globalny stan. To jest kosztowne i zwiększa ryzyko niepowiązanych zmian przy researchu jednego modelu.

Gdzie występuje: [run_model_research_pipeline.py](scripts/run_model_research_pipeline.py:178), [clean_offer_pages_technical.py](scripts/clean_offer_pages_technical.py:258).

Wpływ na użytkownika: czas procesu rośnie wraz z całą kolejką, a wynik jednego researchu może nieoczekiwanie zmienić kontekst innych modeli.

Proponowane rozwiązanie: przekazywać listę nowo pobranych `offer_id` do etapów 4–7; pełną przebudowę zostawić jako osobną komendę maintenance.

Trudność: duża.

### P2-6. Stan klucza API oznacza obecność zmiennej, nie działające uwierzytelnienie

Opis: UI pokazuje „gotowy”, gdy zmienna środowiskowa jest niepusta. Nie może rozpoznać klucza błędnego, wygasłego lub bez uprawnień.

Gdzie występuje: [app.py](app.py:478).

Wpływ na użytkownika: potencjalnie myląca informacja przed uruchomieniem procesu.

Proponowane rozwiązanie: pozostawić obecny stan jako „zmienna ustawiona”, a wynik autoryzacji pokazywać dopiero po bezpiecznym błędzie konkretnego requestu.

Trudność: mała.

## P3 — późniejszy rozwój

### P3-1. Brak prawdziwego wielo-marketplace’owego adaptera

Opis: architektura registry przewiduje wiele marketplace’ów, ale targeted search i runner akceptują dziś tylko Allegro.

Gdzie występuje: [fetch_targeted_model_offers.py](scripts/fetch_targeted_model_offers.py:156), [run_model_research_pipeline.py](scripts/run_model_research_pipeline.py:141).

Wpływ na użytkownika: coverage nie może zostać podniesiony źródłami producenta ani alternatywnymi marketplace’ami.

Proponowane rozwiązanie: dodać adaptery jako oddzielne źródła i zachować wspólny `source_registry`.

Trudność: duża.

### P3-2. Brak kolejki z blokadą i ochrony przed równoległymi uruchomieniami

Opis: runner przepisuje kolejkę CSV i globalne pliki output bez blokady procesu.

Gdzie występuje: [run_model_research_pipeline.py](scripts/run_model_research_pipeline.py:80), [fetch_firecrawl_offer_pages.py](scripts/fetch_firecrawl_offer_pages.py:47).

Wpływ na użytkownika: dwa równoległe uruchomienia mogą pomieszać kolejność i statusy CSV.

Proponowane rozwiązanie: lokalny lock file z PID/timeoutem albo przejście do lekkiej, trwałej kolejki po ustabilizowaniu MVP.

Trudność: średnia.

### P3-3. Brak procesu ręcznego zatwierdzania wartości o średniej pewności i konfliktów

Opis: system zapisuje conflict/open i evidence, ale nie ma ścieżki akceptacji przez człowieka ani historii decyzji.

Gdzie występuje: [extract_model_facts_cascade.py](scripts/extract_model_facts_cascade.py:154), [app.py](app.py:388).

Wpływ na użytkownika: finalny benchmark pozostaje roboczy w polach wymagających decyzji eksperckiej.

Proponowane rozwiązanie: w późniejszym etapie dodać review queue z decyzją, autorem i źródłem; nie nadpisywać oryginalnego evidence.

Trudność: duża.

## Ocena ukończenia MVP

Szacowane ukończenie: **62%**.

Rdzeń jest realny: pobrane karty są czyszczone, źródła są grupowane, istnieje benchmark modelowy, coverage, rekomendacja dalszego researchu oraz czytelny lokalny dashboard. MVP nie jest jeszcze gotowe do samodzielnego pokazania użytkownikom, ponieważ sukces researchu nie jest wystarczająco wiarygodny w obliczu błędów fetchera, katalog modeli jest niepełny, a znaczenie `Apply` jest niejednoznaczne.

## Pięć najważniejszych następnych prac

1. Zmienić kontrakt wyniku fetchera i runnera tak, aby częściowe błędy Firecrawl nie mogły kończyć się fałszywym sukcesem.
2. Rozdzielić tryb podglądu od trybu aplikowania zmian oraz jasno opisać domyślne ustawienia formularza researchu.
3. Pokazać w katalogu wszystkie grupy modeli wraz ze statusem „gotowy / w toku / brak analizy / błąd”.
4. Dodać retry i widok błędów kolejki Firecrawl.
5. Ujednolicić README oraz `docs/APP_SPEC.md` z aktualnym pipeline’em i kanonicznym benchmarkiem.

## Rekomendowana kolejność wdrażania

1. P0-1.
2. P1-1 i P1-2.
3. P1-3 i P1-4.
4. P1-5.
5. P2-1 do P2-5.
6. P3 po potwierdzeniu stabilnego, powtarzalnego researchu Allegro.

## Kryteria uznania MVP za ukończone

- Co najmniej jeden pełny research wybranego modelu z nowymi ofertami kończy się poprawnym, audytowalnym wynikiem: liczba nowych ofert, pobranych kart, błędów, źródeł i zmiana coverage są ze sobą zgodne.
- Żaden błąd pobrania Firecrawl nie jest raportowany jako pełny sukces pipeline’u.
- Użytkownik widzi wszystkie wykryte grupy modeli, również te bez coverage, oraz wie, co trzeba uruchomić dalej.
- Brak kluczy, pusty wynik, błąd pojedynczego pobrania i błąd pipeline’u mają odrębne, zrozumiałe komunikaty oraz nie uszkadzają danych.
- `Apply` i `Skip AI` mają jednoznaczne znaczenie oraz widoczne konsekwencje przed uruchomieniem.
- Dokumentacja opisuje aktualny UI, obecny pipeline i poprawną komendę startową.
- Scenariusze sukcesu, pustego wyniku i błędu mogą być sprawdzane na izolowanych fixtures bez dotykania właściwej kolejki.
