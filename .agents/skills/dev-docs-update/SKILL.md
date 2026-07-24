---
name: dev-docs-update
description: "Utrwala stan aktywnego zadania przed kompaktowaniem, zmianą sesji lub przekazaniem pracy. Użyj, gdy trzeba zachować dokładny kontekst wykonania; nie używaj jako zamiennika review ani ukończenia zadania."
---

# Dev Docs Update

Zapisz stan tak, aby kolejna sesja mogła kontynuować bez ponownego odkrywania pracy.

## Przebieg

1. Ustal aktywne zadanie. Przy wielu katalogach poproś o wskazanie jednego.
2. Zapisz:
   - aktualny branch;
   - `git status --short`;
   - ostatni commit i jego opis;
   - bieżący unit oraz stan `completed|partial|blocked`;
   - testy uruchomione w tej sesji i ich wynik.
3. Zaktualizuj `<slug>-kontekst.md` o:
   - co faktycznie zmieniono i dlaczego;
   - decyzje oraz odchylenia od planu;
   - dokładne pliki/symbole będące w toku;
   - niedokończoną pracę i znane problemy;
   - komendy potrzebne do odtworzenia lub sprawdzenia stanu;
   - jeden konkretny następny krok.
4. Zaktualizuj checklistę bez zgadywania. Zaznacz wyłącznie wykonane i potwierdzone punkty.
5. Zaktualizuj plan wykonawczy tylko, gdy zmieniły się zależności, kolejność lub jawne założenia.
6. Nie używaj `git add .`. Stage'uj tylko pliki bieżącego zadania.
7. Jeśli zmiany kodu są spójne i testy przechodzą, wykonaj normalny commit unitu. Jeśli praca jest częściowa, utwórz WIP commit tylko wtedy, gdy można bezpiecznie objąć nim wyłącznie pliki zadania; w przeciwnym razie pozostaw drzewo brudne i zapisz pełny status.
8. Commituj aktualizację `docs/active/<slug>/` oddzielnie, jeśli nie była częścią commita unitu.

## Sekcja przekazania

Na końcu kontekstu utrzymuj jedną aktualną sekcję:

- branch i commit;
- bieżący unit i status;
- pliki w toku;
- ostatni wynik testów;
- bloker lub brak blokera;
- dokładne polecenie do kontynuacji.

Podaj zaktualizowane pliki i polecenie `$dev-docs-execute docs/active/<slug>`.
