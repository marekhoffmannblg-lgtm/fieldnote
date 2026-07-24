---
name: dev-docs-complete
description: "Zamyka i archiwizuje ukończone zadanie z docs/active do docs/completed, aktualizuje wnioski i status planu. Użyj po przejściu wszystkich unitów i review; nie używaj do ukrywania niedokończonej pracy."
---

# Dev Docs Complete

Zamknij ukończone zadanie bez wdrażania, mergowania ani usuwania historii.

## Przebieg

1. Ustal katalog w `docs/active/` i przeczytaj wszystkie pliki zadania oraz raporty review.
2. Zweryfikuj przed archiwizacją:
   - wszystkie wymagane unity, testy i automatyczne weryfikacje są ukończone;
   - nie ma otwartych P1 ani P2;
   - ręczne kontrole są wykonane albo jawnie zaakceptowane jako odroczone;
   - branch i working tree nie zawierają nieopisanych zmian;
   - końcowy quality gate przeszedł.
3. Gdy warunek nie jest spełniony, nie archiwizuj automatycznie. Wypisz konkretne braki i wróć do `$dev-docs-execute` albo `$dev-docs-review`.
4. Utwórz `<slug>-podsumowanie.md` zawierające:
   - datę ukończenia;
   - dostarczony zakres i jawne non-goals;
   - ważne decyzje;
   - główne zmienione pliki i migracje;
   - uruchomione testy;
   - pozostałe ryzyka lub follow-upy;
   - użyteczne wnioski do ponownego zastosowania.
5. Przenieś cały katalog do `docs/completed/<slug>/`, zachowując raporty review i historię kontekstu.
6. Ustaw status źródłowego planu technicznego na `completed`, jeśli cały jego zakres został wykonany. Nie zmieniaj statusu, gdy aktywne zadanie obejmowało tylko część planu.
7. Dodaj do `docs/solutions/` tylko nietrywialne, powtarzalne rozwiązania. Dodaj do `AGENTS.md` wyłącznie stabilną regułę projektową, nie notatkę jednorazową.
8. Commituj archiwizację i aktualizacje dokumentacji. Nie wykonuj merge, tagu, deploymentu ani usuwania brancha bez osobnego polecenia.

## Wynik

Podaj ścieżkę archiwum, końcowy commit, zestaw testów, kluczowe rezultaty i ewentualne follow-upy.
