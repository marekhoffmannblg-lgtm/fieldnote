---
name: dev-docs
description: "Inicjuje trwały workspace zadania w docs/active na podstawie zatwierdzonego planu technicznego. Użyj po dev-plan, przed implementacją wieloetapowej pracy; nie używaj do pisania kodu ani zastępowania planu technicznego."
---

# Dev Docs

Utwórz trwałą dokumentację wykonawczą zadania. Nie implementuj kodu aplikacji.

## Przebieg

1. Przeczytaj `AGENTS.md`, `docs/CONCEPTS.md`, pasujący dokument wymagań i zatwierdzony plan w `docs/plans/`.
2. Wybierz jeden plan źródłowy. Gdy kilka planów pasuje równie dobrze, zadaj jedno pytanie blokujące.
3. Ustal krótki slug zadania i katalog `docs/active/<slug>/`. Nie twórz duplikatu aktywnego zadania dla tego samego planu.
4. Sprawdź Git:
   - zapisz aktualny branch i `git status --short`;
   - jeśli jesteś na domyślnym branchu i drzewo jest czyste, utwórz `feature/<slug>`;
   - jeśli istnieje właściwy branch zadania, użyj go;
   - jeśli drzewo jest brudne, nie przełączaj brancha i nie usuwaj zmian; zapisz stan w kontekście.
5. Przenieś Implementation Units z planu do checklisty wykonawczej. Zachowaj zależności, pliki testowe, scenariusze testowe i warunki weryfikacji. Nie rozszerzaj scope'u.
6. Utwórz trzy pliki według szablonów w `references/`:
   - `<slug>-plan.md` — skrócony plan wykonawczy i mapowanie faz do unitów;
   - `<slug>-kontekst.md` — stan repo, decyzje, źródła, design, ryzyka i handoff;
   - `<slug>-zadania.md` — checklista implementacji, testów, weryfikacji i review.
7. W obu dokumentach planu i kontekstu zapisz ścieżki do requirements i planu technicznego.
8. W kontekście zapisz designerskie źródła prawdy z frontmatteru planu. Gdy plan wskazuje nieistniejący plik designu, zatrzymaj się i zgłoś bloker.
9. Dodaj datę aktualizacji, branch i ostatni commit.
10. Commituj wyłącznie utworzone pliki `docs/active/<slug>/`; nie stage'uj obcych zmian. Gdy repozytorium nie pozwala bezpiecznie wykonać commita, pozostaw pliki i jasno to odnotuj.

## Granice

- Nie implementuj żadnego Implementation Unit.
- Nie twórz drugiego planu technicznego.
- Nie wykonuj `git add .`.
- Nie zmieniaj wymagań produktowych bez jawnej decyzji użytkownika.
- Jedna faza wykonawcza powinna domyślnie odpowiadać jednemu Implementation Unit.

## Wynik

Podaj katalog aktywnego zadania, branch, plan źródłowy, liczbę unitów i następne polecenie: `$dev-docs-execute docs/active/<slug>`.
