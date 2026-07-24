---
date: 2026-07-23
topic: lionelo-market-intelligence-pipeline
status: ready-for-technical-planning
scope: stroller-mvp
---

# FIELDNOTE — wieloużytkownikowe MVP benchmarku wózków Lionelo

## Problem

Obecny projekt FIELDNOTE ma działający lokalny pipeline researchu, provenance, historię runów, benchmarki i prototyp React/FastAPI, ale stan produkcyjny nadal opiera się głównie na plikach JSON/CSV i pracy na jednym komputerze. Celem jest domknięcie kategorii wózków jako bezpiecznej, wewnętrznej aplikacji webowej dla kilku pracowników BrandLine/Lionelo.

System ma dostarczać orientacyjny obraz rynku, a nie audyt techniczny. Powinien pokazywać najlepszą dostępną wartość, źródła, sprzeczności, świeżość i kompletność danych. Dane z internetu nie są traktowane jako gwarantowana prawda.

## Wynik MVP

MVP obejmuje:

- wszystkie 34 jednostki Lionelo `model + konfiguracja` istniejące obecnie w projekcie,
- wszystkie rzeczywiste marki i modele konkurencji zapisane obecnie w projekcie,
- wykluczenie placeholderów, akcesoriów i rekordów testowych,
- benchmark wewnętrzny całego katalogu Lionelo,
- benchmark zewnętrzny dla wszystkich zgodnych produktowo modeli z aktualnej puli konkurencji,
- ręczny import arkusza `WÓZKI`, ręczny research i ręczne odświeżanie,
- trwałą bazę, logowanie, role, kolejkę zadań, historię i wdrożenie webowe.

Do momentu zamknięcia obecnego zakresu nie dodajemy nowych kategorii, marek ani modeli konkurencji. Następną kategorią będą foteliki.

## Użytkownicy i dostęp

Role:

- **Odbiorca** — odczyt wszystkich produktów, benchmarków, źródeł i historii.
- **Analityk** — odczyt oraz uruchamianie researchu, edycja wartości, segmentów, profili i uczestników benchmarku.
- **Administrator** — uprawnienia analityka oraz import katalogu, zarządzanie kontami i konfiguracją źródeł.

Wszyscy zalogowani użytkownicy widzą cały katalog. Role ograniczają operacje, nie zakres danych.

Logowanie:

- email i hasło,
- brak publicznej rejestracji,
- konto tworzy administrator,
- pierwsze hasło jest tymczasowe i wymaga zmiany,
- SSO jest poza MVP.

## Zakres danych

W aplikacji przechowujemy:

- publiczne specyfikacje Lionelo,
- publiczne specyfikacje konkurencji,
- ceny sprzedaży brutto,
- publiczne źródła, evidence, historię i snapshoty.

Poza MVP pozostają marże, koszty zakupu, plany premier, informacje poufne i integracje z systemami firmowymi.

## Tożsamość produktu

- Jednostką benchmarku jest `marka + model + konfiguracja`.
- Konfiguracje 2w1, 3w1 i 4w1 są osobnymi produktami benchmarkowymi.
- Kolory są ignorowane w benchmarku.
- SKU służy tylko do identyfikacji i deduplikacji w imporcie Lionelo.
- Edycje specjalne, gratisy i zestawy promocyjne są poza MVP.
- Oficjalna nazwa producenta jest nazwą kanoniczną konkurenta.
- Różne nazwy ze sklepów i marketplace'ów są aliasami tego samego modelu.

## Segmenty i porównywalność

MVP korzysta z istniejących grup:

- lekkie spacerówki,
- standardowe spacerówki,
- wózki 2w1,
- wózki 3w1.

Zasady:

- porównujemy wyłącznie produkty z tej samej kategorii i konfiguracji,
- nie porównujemy między segmentami,
- system może proponować profil użytkowy, ale użytkownik może go poprawić,
- ręczna korekta ma pierwszeństwo przed ponowną klasyfikacją automatyczną.

## Katalog Lionelo i import

Kanonicznym źródłem jest arkusz specyfikacji Lionelo z zakładką `WÓZKI`.

MVP używa ręcznego uploadu XLSX w panelu administratora:

1. wgranie pliku,
2. podgląd nowych, zmienionych, błędnych i zduplikowanych rekordów,
3. zatwierdzenie importu.

Nie implementujemy bezpośredniej synchronizacji Google Sheets.

Import nie może tworzyć duplikatów. EOL oznacza archiwizację, nie kasowanie historii. Zachowanie produktu znikającego z kolejnego pliku pozostaje poza MVP.

## Katalog konkurencji

- Marki konkurencyjne są przypisane ręcznie do kategorii wózków.
- Oficjalna strona kategorii producenta definiuje katalog modeli marki.
- Administrator ręcznie uruchamia `Odśwież katalog marki`.
- Firecrawl pobiera stronę kategorii i karty produktowe.
- System pokazuje podgląd nowych, zmienionych i znikających modeli przed zapisem.
- Allegro, Amazon i sklepy branżowe uzupełniają parametry, ceny i dostępność; nie definiują katalogu marki.
- Zwykłe odświeżenie benchmarku nie wyszukuje nowych konkurentów.

## Źródła i pobieranie

Dozwolone źródła MVP:

- oficjalne strony producentów,
- Allegro,
- Amazon,
- ręcznie wybrane sklepy branżowe.

Wszystkie źródła zewnętrzne są pobierane przez Firecrawl. Nie budujemy własnych scraperów i nie wykonujemy ogólnego crawlowania internetu.

Wszystkie źródła przechodzą przez wspólny lifecycle:

`discover → fetch → normalize → classify → evidence → aggregate → snapshot`.

Dla każdego pobrania zapisujemy:

- surowy snapshot w Storage,
- oczyszczoną treść,
- dane strukturalne w PostgreSQL,
- URL, typ źródła, datę pobrania i content hash,
- evidence per atrybut.

## Atrybuty wózków

Obecny schemat 21 pól jest bazą roboczą, nie finalną listą punktowaną.

Przed zamknięciem scoringu wykonujemy jednorazowy audyt na 12–16 istniejących modelach konkurencji, po 3–4 z każdej grupy, o ile aktualny katalog na to pozwala. Raport ocenia:

- pokrycie atrybutu,
- liczbę i niezależność źródeł,
- sprzeczności,
- możliwość normalizacji,
- zdolność różnicowania produktów.

Po audycie każde pole otrzymuje rolę:

- punktowane,
- informacyjne,
- identyfikacyjne,
- odrzucone z benchmarku.

Nie ustalamy z góry procentowego progu pokrycia.

Schemat wózków jest wersjonowanym plikiem YAML/JSON w repozytorium. Nie budujemy edytora schematów w aplikacji.

Każdy atrybut ma:

- kanoniczny klucz,
- aliasy nazw,
- typ wartości,
- jednostkę bazową,
- reguły konwersji i normalizacji,
- rolę w benchmarku,
- wagi per profil.

## Benchmark wewnętrzny Lionelo

- Obejmuje tylko produkty Lionelo.
- Powstaje dla grup zawierających minimum 3 porównywalne modele.
- Dla dwóch modeli pokazujemy zwykłe porównanie bez rankingu portfolio.
- Wyniki są liczone osobno dla profili użytkowych.
- Benchmark pokazuje pozycję, wynik względny, kompletność danych i wpływ parametrów.
- Cena nie wpływa na wynik użytkowy.

## Benchmark zewnętrzny

- Research uruchamia człowiek dla jednego produktu naraz.
- Dwóch użytkowników może uruchomić research różnych produktów; maksymalnie działają dwa zadania równolegle.
- Ten sam produkt nie może mieć dwóch aktywnych researchów.
- System używa wyłącznie aktualnej puli konkurentów zapisanych w projekcie.
- Benchmark może zawierać do 6 dopasowanych konkurentów, ale brak pełnej szóstki nie blokuje wyniku.
- Lista uczestników jest stała między zwykłymi odświeżeniami i może być ręcznie zmieniana.

## Scoring

- `src/scoring.py` pozostaje mechanizmem weryfikacji dopasowania oferty do marki i modelu.
- Ranking produktowy otrzymuje osobny mechanizm.
- Nie używamy stałych progów punktowych dla wszystkich kategorii.
- Wynik jest względny wyłącznie wobec produktów w tym samym segmencie.
- Parametry są normalizowane w obrębie grupy, a następnie ważone profilem.
- Brak danych nie daje zera; obniża wskaźnik kompletności.
- Cena jest prezentowana osobno i nie wpływa na ranking użytkowy.
- AI może wydobywać i normalizować fakty, ale nie oblicza końcowego rankingu.
- Automatyczne wnioski strategiczne i rekomendacje AI są poza MVP.

## Ceny

- Liczymy ceny brutto nowych, dostępnych produktów w identycznej konfiguracji.
- Pomijamy używane, powystawowe, niedostępne, warunkowe kupony i koszt dostawy.
- Promocje są oznaczane.
- Ten sam sprzedawca w wielu kanałach jest deduplikowany.
- Widok pokazuje medianę oraz zakres min–max.
- Cena zwykła jest świeża 14 dni, promocyjna 3–7 dni.

## Dostępność

Dostępność jest funkcją pomocniczą.

- zapisujemy stan per źródło,
- pokazujemy status rynkowy: dostępny, ograniczony, niedostępny albo nieznany,
- próg roboczy prawdopodobnego wycofania wynosi 90 dni,
- nie rozbudowujemy zaawansowanej analityki dostępności w MVP.

## Historia i snapshoty

- Każdy research zapisuje run i zużycie Firecrawl/OpenAI.
- Nowy snapshot powstaje tylko przy istotnej zmianie.
- Istotna zmiana obejmuje wartość parametru, konflikt, poziom zaufania, listę uczestników, ranking, medianę ceny o minimum 5%, status promocji albo status rynkowy.
- Ponowne pobranie identycznych danych nie tworzy snapshotu.
- Ręczne poprawki są audytowane: użytkownik, czas, poprzednia i nowa wartość.

## Research i kontrola kosztów

Każdy research ma konfigurowalne limity:

- maksymalna liczba stron,
- maksymalny budżet tokenów AI,
- timeout,
- retry.

Po przekroczeniu limitu run kończy się jako `partial`, zachowując poprawnie zebrane dane. Dokończenie wymaga ręcznego uruchomienia.

Research działa przyrostowo:

- aktualizuje wybrany model,
- przelicza tylko powiązane benchmarki i grupę wewnętrzną,
- nie przebudowuje całego katalogu.

Pełna przebudowa katalogu jest osobną akcją administratora.

## Architektura docelowa

Zachowujemy istniejące technologie i działającą logikę:

- React/Vite — frontend,
- FastAPI — API,
- istniejący pipeline Python — research i przetwarzanie,
- Supabase — PostgreSQL, Auth i Storage,
- Render — frontend, API i background worker,
- prywatne repozytorium GitHub — kod i CI.

Pipeline najpierw zostaje opakowany w trwały worker. Refaktor skryptów następuje stopniowo, bez przepisywania wszystkiego od zera.

## Kolejka zadań

- Zadanie jest zapisywane w PostgreSQL i działa po zamknięciu przeglądarki.
- Worker odbiera zadania z kolejki.
- Maksymalnie dwa research jobs działają równolegle.
- Nadmiar czeka.
- Ten sam produkt jest blokowany na czas aktywnego zadania.
- Globalne operacje agregacyjne są wykonywane pojedynczo.
- Statusy: queued, running, success, partial, failed, cancelled.

## Migracja danych

Migracja jest etapowa:

1. wprowadzenie interfejsów repozytoriów,
2. PostgreSQL jako główne źródło danych,
3. selektywny import wartościowych danych,
4. pozostawienie plików jako archiwum tylko do odczytu i artefakty diagnostyczne,
5. wyłączenie plikowego stanu produkcyjnego po porównaniu wyników.

Przenosimy:

- 34 produkty Lionelo i ich specyfikacje,
- rzeczywiste modele konkurencji z obecnego katalogu,
- źródła i evidence z poprawnym provenance,
- przydatne surowe snapshoty.

Nie migrujemy automatycznie wszystkich historycznych plików i niespójnych outputów.

## Testy

- CI nie wywołuje Firecrawl ani OpenAI.
- Testy korzystają z zapisanych fixtures odpowiedzi zewnętrznych i stałych odpowiedzi AI.
- Testy obejmują import, normalizację, provenance, konflikty, scoring, ceny, snapshoty, role, kolejkę i incremental rebuild.
- Płatny test live jest ręczny i wykonywany przed większym wydaniem.

## Bezpieczeństwo przed wdrożeniem

Aplikacja nie trafia do internetu przed spełnieniem bramki:

- dwa oddzielne środowiska: staging i production,
- HTTPS,
- wyłączona publiczna rejestracja,
- brak sekretów w frontendzie i repozytorium,
- RLS w bazie i prywatne bucket'y Storage,
- role po stronie API i bazy,
- limity logowania oraz API,
- skan sekretów i zależności w CI,
- backup bazy i audyt zmian,
- MFA na kontach administrujących Supabase i Render.

## Interfejs MVP

Główne widoki:

- logowanie i wymuszona zmiana pierwszego hasła,
- katalog produktów,
- szczegóły produktu,
- benchmark wewnętrzny,
- benchmark zewnętrzny,
- źródła i evidence,
- runy i kolejka,
- import XLSX dla administratora,
- zarządzanie użytkownikami dla administratora.

Samouczek kontekstowy zostaje odroczony do czasu stabilizacji UI.

## Poza MVP

- foteliki i pozostałe kategorie,
- nowe marki i modele poza obecnym katalogiem,
- recenzje i social media jako aktywny moduł analizy,
- automatyczne wnioski strategiczne i rekomendacje AI,
- automatyczne cykliczne odświeżanie,
- masowy research uruchamiany jednym kliknięciem,
- SSO,
- bezpośrednia synchronizacja Google Sheets,
- integracje PIM/ERP/sprzedażowe,
- kolory i zestawy promocyjne,
- administracyjny edytor schematów kategorii,
- pełna migracja wszystkich starych outputów.

Model danych powinien jednak od początku dopuszczać typy źródeł `review` i `social`, aby późniejsza rozbudowa nie wymagała drugiego pipeline'u.

## Kryteria ukończenia MVP

- Wszystkie 34 produkty Lionelo są w PostgreSQL, widoczne i poprawnie pogrupowane.
- Wszystkie rzeczywiste modele konkurencji z aktualnego projektu są sklasyfikowane albo jawnie oznaczone jako wykluczone.
- Benchmark wewnętrzny działa dla każdej grupy z minimum 3 modelami.
- Każdy zgodny produkt Lionelo może otrzymać benchmark z aktualnej puli konkurentów.
- Research działa w tle, przeżywa zamknięcie przeglądarki i nie przebudowuje całego katalogu.
- Każda wartość ma provenance albo status legacy/nieprzypisana.
- Ceny pokazują medianę i min–max bez wpływu na wynik użytkowy.
- Snapshot powstaje wyłącznie przy istotnej zmianie.
- Role, RLS i brak publicznej rejestracji są zweryfikowane.
- CI przechodzi bez płatnych API.
- Staging i production są odseparowane, a produkcja przechodzi bramkę bezpieczeństwa.

## Otwarte kwestie odroczone do implementacji

- Dokładne mapowanie niejednoznacznych modeli Kinderkraft do grup 2w1/3w1 na podstawie oficjalnych stron.
- Finalna lista atrybutów punktowanych po jednorazowym audycie danych.
- Finalna strategia deduplikacji sprzedawców, gdy źródło nie ujawnia jednoznacznej firmy.
- Kosztowe limity Firecrawl i OpenAI po pierwszych kontrolowanych runach stagingowych.
- Docelowa retencja surowych snapshotów po obserwacji rzeczywistego zużycia Storage.
