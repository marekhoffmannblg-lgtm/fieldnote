# UX Redesign

## Główne zadania użytkownika

1. Zobaczyć produkty zapisane w systemie.
2. Sprawdzić jakość danych konkretnego modelu.
3. Porównać gotowe modele.
4. Znaleźć nowe dane dla produktu.
5. Zrozumieć wynik uruchomionego researchu.
6. Naprawić nieudane pobranie.
7. Podłączyć Firecrawl i OpenAI bez terminala.

## Mapa ekranów

- **Start**: trzy główne działania, produkty wymagające uwagi, ostatnie uruchomienia i błędy.
- **Produkty**: katalog z wyszukiwaniem i filtrami.
- **Porównanie**: zestawienie dwóch do pięciu gotowych benchmarków.
- **Szczegóły produktu**: osobna strona z breadcrumbem oraz zakładkami: Podsumowanie, Dane produktu, Źródła, Braki i konflikty, Historia researchu.
- **Nowy research**: sześciostopniowy kreator.
- **Kolejka**: bieżący stan pobrań i bezpieczne ponowienie pojedynczej oferty.
- **Uruchomienia**: monitor wykonanych procesów i ich etapów.
- **Integracje**: lokalne połączenia Firecrawl i OpenAI zapisane w systemowym magazynie haseł.
- **Pomoc**: odpowiedzi organizowane według zadań użytkownika.

## Pierwsze uruchomienie

Na ekranie Start użytkownik widzi krótką kartę „Skonfiguruj aplikację w 3 krokach”: podłącz Firecrawl, podłącz OpenAI, uruchom pierwszy research. Może ją pominąć i od razu przeglądać istniejące dane. Pełny samouczek jest dobrowolny i można go uruchomić ponownie z Pomocy.

## Przepływ researchu

1. **Produkt**: wybór produktu lub wpisanie marki i modelu.
2. **Integracje**: sprawdzenie wymaganych połączeń i przejście do ich konfiguracji, jeśli ich brakuje.
3. **Sprawdzenie ofert**: bezpieczny podgląd ofert bez zmiany benchmarku.
4. **Potwierdzenie**: jasne podsumowanie danych, które zostaną pobrane i zaktualizowane.
5. **Realizacja**: status dziewięciu etapów i postęp, z detalami technicznymi wyłącznie w expanderze.
6. **Wynik**: status, liczniki, zmiana pokrycia oraz działania przejścia do produktu lub uruchomienia.

## Obsługa błędów

Błąd jest widoczny na stronie Uruchomienia i na Start jako zadanie wymagające działania. Użytkownik widzi produkt, etap, przyczynę oraz bezpieczną akcję ponowienia pobrania. Szczegóły techniczne pozostają zwinięte. Rekordy kolejki z błędem są dostępne jako czytelne karty, nie jako CSV.

## Zasady nawigacji

- Stała lewa nawigacja prowadzi do Start, Produkty, Porównanie, Nowy research, Kolejka, Historii, Integracji i Pomocy.
- Szczegóły produktu mają breadcrumb `Produkty / Marka / Model` oraz przycisk powrotu.
- Produkt, uruchomienie i krok kreatora są kodowane w parametrach URL. Odświeżenie i cofnięcie w przeglądarce zachowują kontekst.
- Filtry katalogu są zapisywane w URL przed przejściem do szczegółów.
- Techniczne identyfikatory nie są elementem głównej nawigacji.

## Stany interfejsu

- **Pusty**: wyjaśnia, jak dodać pierwsze dane i pokazuje jedną akcję.
- **Ładowanie**: wskazuje aktualny krok oraz ogólny postęp.
- **Sukces**: potwierdza wynik i prowadzi do produktu lub uruchomienia.
- **Częściowy sukces**: podkreśla liczbę pobranych i błędnych ofert oraz umożliwia ponowienie.
- **Błąd**: mówi, co nie zadziałało i proponuje bezpieczne następne działanie.
