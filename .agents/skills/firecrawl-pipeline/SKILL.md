---
name: firecrawl-pipeline
description: "Projektuje i implementuje pipeline researchu produktów przez Firecrawl oraz ekstrakcję AI z pełnym provenance, snapshotami, konfliktami i limitami kosztu. Użyj przy producentach, Allegro, Amazonie i sklepach branżowych."
---

# Firecrawl Pipeline

## Dozwolone źródła MVP

- oficjalne strony producentów;
- Allegro;
- Amazon;
- ręcznie wybrane sklepy branżowe.

W produkcji wszystkie strony pobieraj przez Firecrawl. Bezpośredni HTTP może pozostać wyłącznie narzędziem developerskim.

## Lifecycle

1. Przyjmij model+konfigurację i zatwierdzone URL-e lub katalog marki.
2. Pobierz surowy snapshot oraz metadane czasu i źródła.
3. Zapisz snapshot w Storage przed ekstrakcją.
4. Wyciągnij kanoniczne atrybuty kategorii, zachowując excerpt i source id.
5. Normalizuj aliasy nazw oraz jednostki.
6. Agreguj wartości według priorytetu źródła, ale zachowaj alternatywy i sprzeczności.
7. Oblicz kompletność, ceny i benchmark tylko dla dotkniętego modelu i jego grupy.
8. Zapisz run zawsze; snapshot benchmarku tylko po istotnej zmianie.

## Kontrola kosztu i jakości

- Ustal limit stron, czasu i tokenów dla runu.
- Po limicie zakończ jako `partial`, nie kontynuuj automatycznie.
- AI używaj dopiero po prostszej ekstrakcji i tylko dla brakujących pól.
- Cena: nowe, dostępne produkty w tej samej konfiguracji; deduplikuj sprzedawców; licz medianę oraz min-max.
- Testy korzystają z zapisanych fixtures Firecrawl i deterministycznych odpowiedzi AI.
- Nie traktuj liczby skopiowanych opisów jako liczby niezależnych potwierdzeń.
