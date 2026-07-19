# FIELDNOTE Function Matrix

Audyt wykonano 15.07.2026 lokalnie, bez pobierania nowych danych i bez wywołań OpenAI. `WORKING` oznacza funkcję potwierdzoną kodem i testem end-to-end, a nie samo istnienie komponentu lub endpointu.

| Obszar | Funkcja | Status | Dowód | Wpływ | Priorytet | Rekomendacja |
|---|---|---|---|---|---|---|
| Uruchamianie | Start backendu i frontendu na 8000/5173 | WORKING | `scripts/start_fieldnote_local.sh`; oba healthchecki HTTP 200 | Aplikacja startuje jedną komendą | P2 | Zachować kontrakt portów |
| Uruchamianie | `status` i healthcheck | WORKING | Test lokalny pokazał oba procesy jako running/healthy | Użytkownik widzi stan usług | P3 | Poprawić tylko prezentację starego PID |
| Uruchamianie | `stop` ograniczony do procesów FIELDNOTE | PARTIALLY_WORKING | Skrypt zatrzymuje PID-y, ale również dowolnych listenerów na 5173/5174/8000 | Może zakończyć obcy proces | P1 | Zabijać port tylko po potwierdzeniu ownership |
| Uruchamianie | Działanie po zamknięciu terminala | WORKING | Procesy uruchamiane przez `nohup`, stdin `/dev/null`, logi w `/tmp` | Brak zawieszenia TTY | P3 | Dodać rotację logów |
| Uruchamianie | Stabilność długich runów | PARTIALLY_WORKING | Uvicorn pracuje z `--reload` i obserwuje repo | Zmiana pliku może ubić wątek procesu | P0 | Wyłączyć reload w zwykłym starcie |
| Produkty | Katalog 14 produktów | WORKING | UI i `catalog.json` pokazują 14 unikalnych produktów | Podstawowa nawigacja działa | P3 | Zachować |
| Produkty | Wyszukiwanie i filtry | WORKING | Test przeglądarkowy katalogu; `App.tsx` | Szybkie odnajdywanie modelu | P3 | Dodać test komponentowy |
| Produkty | Grupowanie marka/kategoria | WORKING | UI grupuje CYBEX i Kinderkraft | Katalog jest czytelny | P3 | Po naprawie taksonomii zachować |
| Produkty | Statusy produktu | BROKEN | `products.json` ma 14x `waiting_for_analysis`, UI ma 5 ready/2 failed/7 refresh | Użytkownik nie ma wiarygodnego statusu | P0 | Jedno kanoniczne wyliczanie stanu |
| Produkty | Coverage | PARTIALLY_WORKING | 5 wyników zgodnych z CSV, lecz zależnych od błędnej taksonomii/evidence | Liczba może sugerować fałszywą jakość | P1 | Liczyć po rewalidacji i poprawnej kategorii |
| Produkty | Liczba braków | BROKEN | APINO/ESME bez finalnych pól pokazują `0` braków | Brak analizy wygląda jak kompletność | P1 | Pokazywać `—` dla nieanalizowanych |
| Produkty | Routing do konkretnego modelu | WORKING | CDP: katalog → ORFEO, back, reload i direct URL działają | Nawigacja podstawowa jest stabilna | P3 | Zachować |
| Research | Formularz marka/model | WORKING | UI `/research`; test Bugaboo Butterfly 2 | Umożliwia nowy research | P2 | Dodać test UI |
| Research | Izolacja stanu kolejnego produktu | WORKING | `check_research_state_isolation.py`; brak ORFEO w teście Butterfly 2 | Brak przeciekania poprzedniego produktu | P2 | Zachować cache key per produkt |
| Research | Preview z lokalnego cache | WORKING | NEBO API 200, `mode=local_cached_listing`, 20 ofert, 0 fetchy | Bezpieczny podgląd działa offline | P2 | Jawnie oznaczać wiek cache |
| Research | Dokładne dopasowanie modelu | PARTIALLY_WORKING | NEBO tokenowo poprawne; Butterfly 2 odróżnia poprzednią generację | Rdzeń działa, reguły kategorii są niepełne | P1 | Centralny klasyfikator i fixtures per marka |
| Research | Odrzucanie akcesoriów | PARTIALLY_WORKING | `materac` NEBO sklasyfikowany jako unknown, nie accessory | Statystyki i ranking są zaniżone | P1 | Rozszerzyć słownik i testy kontekstowe |
| Research | Top 10 / supplementary | WORKING | Cached listing i endpoint zwracają rozdzielone listy | Kontroluje koszt źródeł | P2 | Zachować deterministyczny ranking |
| Research | Oficjalne źródła w wyborze | PARTIALLY_WORKING | NEBO pokazuje 1 manufacturer; brak szerokiej walidacji innych marek | Pierwsze źródło pierwotne działa | P2 | Ustalić kontrakt adaptera manufacturer |
| Research | Potwierdzenie i start runu | WORKING | Frontend wywołuje `/api/research/run`, zapisuje run_id i polluje | Główny przepływ jest połączony | P1 | Dodać idempotency key |
| Research | Polling bieżącego runu | PARTIALLY_WORKING | Działa w czasie życia procesu API; stan w pliku | Po restarcie API aktywna praca nie jest wznawiana | P0 | Trwały worker/lease i recovery |
| Research | Retry failed runu | PARTIALLY_WORKING | Endpoint istnieje; logika zależy od lokalnego statusu i procesu | Retry może nie odtworzyć dokładnego kontekstu | P1 | Zapisać pełny immutable run context |
| Pipeline | Preview bez `--apply` | WORKING | Runner kończy `pipeline_status=preview`, tylko etap 1 | Podgląd nie zmienia benchmarku | P2 | Zachować |
| Pipeline | Targeted search i merge | WORKING | `check_targeted_model_fetcher.py` OK | Wykrywa nowe offer_id i deduplikuje | P2 | Utrzymać testy regresyjne |
| Pipeline | Firecrawl success/partial/failed | WORKING | Fetcher raportuje run-local counters; runner propaguje status | Błąd pobrania nie jest zielonym sukcesem | P1 | Dodać integracyjny test z mock HTTP |
| Pipeline | Timeouty HTTP | WORKING | Requesty Firecrawl/producent mają timeouty 120/30 s | Ogranicza wiszące połączenia | P2 | Ujednolicić retry/backoff |
| Pipeline | Timeout procesu/subprocess | BROKEN | `subprocess.run`, `Popen.wait/read` bez timeoutu | Pipeline może wisieć bez końca | P0 | Timeout per stage + cancel + terminal state |
| Pipeline | Incremental cleaner/registry/groups | WORKING | Filtry offer IDs i group key w runnerze/skryptach | Research nie musi dotykać całego zbioru | P2 | Dodać manifest touched files |
| Pipeline | Resume | PARTIALLY_WORKING | Pomija przetworzone dane, ale brak transakcyjnego checkpointu | Po awarii możliwe niejednoznaczne wznowienie | P0 | Checkpoint stage + input/output hashes |
| Pipeline | `--no-fetch` w kanonicznym runnerze | NOT_IMPLEMENTED | Opcja występuje w migracji, nie w głównym runnerze | Trudniej bezpiecznie analizować tylko snapshoty | P2 | Jawny tryb local-only w runnerze |
| Pipeline | Cleaner outputs | PARTIALLY_WORKING | Funkcjonalne checkery OK, ale 5 plików zapisywanych nieatomowo | Przerwanie może zostawić pół-bundle | P0 | Temp directory + atomic rename |
| Pipeline | Source registry | WORKING | 41 unikalnych source_id, brak brakujących snapshotów | Rejestr jest użyteczny | P1 | Dołożyć walidację assignment i schema version |
| Pipeline | Model grouping | PARTIALLY_WORKING | Kanoniczne foldery i brak duplikatów; 7 rekordów registry bez przypisania | Nie wszystkie poprawne źródła trafiają do grup | P1 | Raport unassigned i deterministyczna polityka cap |
| Pipeline | AI cascade validation | PARTIALLY_WORKING | Testy walidatora przechodzą, lecz historyczne stany zawierają błędne evidence | Finalne dane mogą być semantycznie fałszywe | P0 | Rewalidacja wszystkich stanów przed dalszym AI |
| Pipeline | Benchmark build | PARTIALLY_WORKING | 5 wierszy powstaje; kategoria porównawcza jest błędna dla MOOV | Porównanie nie jest domenowo wiarygodne | P0 | Naprawić taksonomię przed benchmarkiem |
| Pipeline | Coverage report | PARTIALLY_WORKING | Liczby generują się, ale dziedziczą błędy evidence i kategorii | Coverage nie równa się jakości | P1 | Coverage z valid/confirmed provenance |
| Pipeline | Frontend snapshot export | WORKING | Generuje 14 produktów, frontend build czyta dane | UI ma lokalny snapshot danych | P2 | Dodać schema/version timestamp |
| Pipeline | Odporność na równoległe runy | BROKEN | Brak locków; wspólne CSV/JSON i globalny benchmark | Ryzyko nadpisania kolejki, state i wyników | P0 | Lock per product + global lock dla agregatów |
| Produkt | Finalna specyfikacja | PARTIALLY_WORKING | 5 modeli renderuje pola; wykryto błędy ORFEO/NEBO/MOOV | Wynik wygląda pewnie mimo błędów | P0 | Rewalidacja i quality gate |
| Produkt | Provenance wielu źródeł | PARTIALLY_WORKING | Struktury dict/list/string/null obsługiwane; 8 excerpt-only bez source_id | Części dowodów nie da się audytować do URL | P1 | Backfill tylko przy zachowanym snapshot/source mapping |
| Produkt | Konflikty | PARTIALLY_WORKING | NEBO pokazuje konflikt; ORFEO ma konflikt w evidence bez statusu conflicting | Konflikty mogą zostać ukryte | P0 | Deterministyczna normalizacja i conflict detection |
| Produkt | Raw/clean snapshot | WORKING | API snapshot 200; 40 raw i 40 clean, lokalna ścieżka ograniczona | Dowód pozostaje po zniknięciu aukcji | P2 | Dodać content type i rozmiar |
| Źródła | Rozliczenie ORFEO 10 ofert | WORKING | `check_product_sources.py`: 10 selected, 8 fetched, 2 failed | Widok nie gubi pobranych/failed | P2 | Rozszerzyć analogiczny audit na inne modele |
| Źródła | Cena i sprzedawca | PARTIALLY_WORKING | ORFEO prices recovered; invalid seller labels filtered; nie wszystkie listingi mają dane | Puste pola są nadal częste | P2 | Pokazywać brak kolumny, gdy dane nieobecne |
| Źródła | Wkład źródła | PARTIALLY_WORKING | Endpoint zwraca nowe/potwierdzone/konflikty/zero contribution | Pierwsze źródło zależy od kolejności evidence, nie czasu | P1 | Użyć chronology + content_family independence |
| Źródła | Niedostępne URL z zachowanym snapshotem | WORKING | Model API zachowuje snapshot i evidence niezależnie od URL | Nie traci audytowalności | P2 | Dodać okresowy, tani status check |
| Benchmark | Porównanie wielu modeli | WORKING | API/UI porównało ORFEO, MOOV, NEBO, TIK, TRIG 3 | Zakładka nie jest kopią jednego produktu | P1 | Nie eksponować do decyzji przed taxonomy fix |
| Benchmark | Dobór tej samej kategorii | BROKEN | Wszystkie 14 modeli dostało domyślne `Spacerówki lekkie` | Porównywane są nieporównywalne produkty | P0 | Jawne reguły kategorii i migracja |
| Historia | Historia wersji produktu | PARTIALLY_WORKING | Niektóre produkty mają refresh manifests; NEBO 0 wersji | Brak pełnej osi zmian | P1 | Jeden manifest runu + wersja wyniku |
| Historia | Globalna lista uruchomień w UI | MOCK_ONLY | `App.tsx` renderuje stałą tablicę `RUNS` | Użytkownik widzi fikcyjne runy | P0 | Czytać rzeczywiste manifesty API |
| Historia | Retry z ekranu Uruchomienia | MOCK_ONLY | `setTimeout`, brak wywołania backendu | Akcja pozornie działa | P0 | Podłączyć endpoint retry albo usunąć akcję |
| Historia | Zachowanie po restarcie API | BROKEN | Worker jest w daemon thread, nie ma recovery aktywnego procesu | Run może zostać wiecznie running | P0 | Persistent worker state/reconciler |
| Katalog | Slugi i group_key | WORKING | 14 unikalnych, brak orphan/duplicate group | Tożsamość modeli jest stabilna | P2 | Dodać constraint przy zapisie |
| Katalog | Taksonomia kategorii | BROKEN | `catalog_registry.py` stosuje jedną domyślną benchmark_category | Benchmark jest domenowo niepoprawny | P0 | Wymagać jawnej kategorii przy rejestracji |
| API | Health bez sekretów | WORKING | `/api/health` zwraca tylko booleany | Klucze nie wyciekają | P2 | Zachować |
| API | Walidacja slug/source/snapshot path | WORKING | Walidatory i `resolve` pod `PROJECT_ROOT`; test snapshot 200 | Brak potwierdzonego traversal | P2 | Dodać testy negatywne |
| API | CORS lokalny | WORKING | Tylko localhost/127.0.0.1:5173 | Odpowiednie dla lokalnego MVP | P3 | Konfigurować przy deploymencie |
| API | Kontrakty i typowanie odpowiedzi | PARTIALLY_WORKING | Pydantic requesty, lecz wiele odpowiedzi to luźne dict i pliki | Zmiana formatu może zepsuć UI | P2 | Response models i schema version |
| API | Paginacja/limity dużych odpowiedzi | NOT_IMPLEMENTED | Sources i evidence zwracane w całości | Ryzyko przy skali Amazon/multi-market | P3 | Paginacja i lazy evidence |
| Frontend | Build Vite | WORKING | `npm run build` zakończony sukcesem | Paczka produkcyjna powstaje | P1 | Wymusić typecheck w build |
| Frontend | TypeScript strict check | BROKEN | 3 błędy w `App.tsx` (TS2367, `.at`) | Build przepuszcza błędy typów | P1 | Naprawić i podpiąć `tsc --noEmit` do CI/build |
| Frontend | Błędy runtime | PARTIALLY_WORKING | Główne ścieżki bez crashy; konsola ma favicon 404 | Mały defekt, ale brak automatycznych testów UI | P3 | Dodać favicon i smoke test |
| Frontend | Integracje | MOCK_ONLY | Fikcyjne klucze maskowane, liczniki i save przez timer | Ekran sugeruje realną konfigurację | P0 | Oznaczyć demo lub podłączyć bezpieczne API |
| Frontend | Nawigacja boczna desktop | PARTIALLY_WORKING | Widoczny przycisk X nie zmienia stałego `collapsed=false` | Martwa kontrolka dezorientuje | P2 | Usunąć kontrolkę albo wdrożyć prawdziwy stan |
| Frontend | Loading/error/empty states | PARTIALLY_WORKING | Research ma stany, ale historia/statusy/braki bywają mylące | Nie każdy błąd jest interpretowalny | P2 | Wspólne komponenty stanów |
| Frontend | Hardcoded dane użytkownika/wersji | MOCK_ONLY | `Jan Kowalski`, `Pro Workspace`, `v0.9.1-beta` | Produkt wygląda na zasilany kontem, którego nie ma | P2 | Usunąć lub jawnie oznaczyć demo |
| Testy | Skrypty diagnostyczne | PARTIALLY_WORKING | 33 `check_*.py`; kluczowe checkery przeszły | Dają regresje, ale są ad hoc | P2 | Stopniowo przenieść do pytest |
| Testy | Automatyczny zestaw unit/integration/UI | NOT_IMPLEMENTED | Brak pytest/vitest/Jest/test runnera | Brak stałej bramki jakości | P1 | Minimalny CI: types, unit, fixture E2E |
| Bezpieczeństwo | Ochrona sekretów | WORKING | `.env` 0600, ignorowany; scan poza `.env` bez sekretów | Dobre minimum lokalne | P2 | Rozszerzyć `.gitignore` |
| Bezpieczeństwo | Atomowe zapisy krytycznych plików | PARTIALLY_WORKING | Registry/snapshot export atomowe, state/group/benchmark/clean bundle nie | Przerwanie może uszkodzić wynik | P0 | Wspólny atomic writer/transaction bundle |
| Repozytorium | Higiena artefaktów | BROKEN | 990 MB, node_modules/.venv/zipy/pycache; `.gitignore` ma 2 wpisy | Trudne backupy i przypadkowe paczkowanie sekretów | P1 | Uzupełnić ignore i osobny cleanup po akceptacji |

## Bilans

- WORKING: 29
- PARTIALLY_WORKING: 26
- BROKEN: 9
- MOCK_ONLY: 4
- NOT_IMPLEMENTED: 3
- UNCLEAR: 0

Ocena funkcji uwzględnia rzeczywiste testy lokalne. Funkcje oznaczone `PARTIALLY_WORKING` nie powinny być traktowane jako gotowe do skalowania na nowe marketplace'y.
