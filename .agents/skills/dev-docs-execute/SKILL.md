---
name: dev-docs-execute
description: "Wykonuje dokładnie jeden nieukończony Implementation Unit z zadania w docs/active, uruchamia testy i aktualizuje trwały kontekst. Użyj do kontynuowania zatwierdzonego zadania; nie używaj do wykonywania całego planu naraz."
---

# Dev Docs Execute

Wykonaj dokładnie jeden Implementation Unit z aktywnego zadania.

## Przebieg

1. Ustal katalog zadania w `docs/active/`. Jeśli nie został podany, wybierz jedyny aktywny katalog; przy wielu poproś o wskazanie jednego.
2. Przeczytaj w tej kolejności:
   - `AGENTS.md` i `docs/CONCEPTS.md`;
   - trzy pliki zadania;
   - źródłowy requirements doc i plan techniczny;
   - ostatni raport review, jeśli istnieje.
3. Wybierz wskazany unit albo pierwszy nieukończony unit, którego zależności są spełnione. Nie rozpoczynaj kolejnego unitu w tym samym uruchomieniu.
4. Sprawdź branch, `git status --short` i ostatni commit. Nie nadpisuj istniejących zmian i nie przełączaj brancha przy brudnym drzewie.
5. Użyj subagenta `explorer`, gdy ścieżki lub rzeczywisty flow nie są potwierdzone. Następnie:
   - użyj `data_builder` dla FastAPI, Supabase, workerów, pipeline'u i migracji;
   - użyj `ui_builder` dla Reacta i interakcji;
   - dla pracy przekrojowej wykonuj zmiany seryjnie, nigdy przez kilku agentów edytujących te same pliki.
   Gdy delegacja nie jest dostępna, główny agent może wykonać unit, zachowując te same granice.
6. Przed zmianą kruchego legacy zachowania dodaj test charakterystyczny lub fixture. Testy automatyczne nie mogą wywoływać płatnych API.
7. Zaimplementuj najmniejszą spójną zmianę wymaganą przez unit. Nie wykonuj sąsiedniego refaktoru ani elementów poza zakresem.
8. Uruchom testy wskazane w planie, następnie najwęższy repozytoryjny quality gate. Nie zaznaczaj PASS bez faktycznego uruchomienia.
9. Zaktualizuj:
   - checkboxy implementacji, testów i weryfikacji w `<slug>-zadania.md`;
   - stan, zmienione pliki, decyzje, wyniki testów i następny krok w `<slug>-kontekst.md`;
   - plan wykonawczy tylko wtedy, gdy odkrycie zmienia kolejność lub zależności.
10. Po zielonej weryfikacji commituj kod i dokumentację unitu jednym logicznym commitem. Stage'uj wyłącznie pliki należące do unitu.
11. Przy stanie `partial` lub `blocked` nie udawaj ukończenia. Zapisz dokładny stan i pytanie/bloker w kontekście; nie zaznaczaj unitu jako zakończonego.

## Status końcowy

Zwróć jeden status:

- `completed` — unit wdrożony, testy przeszły, dokumentacja zaktualizowana;
- `partial` — praca zachowana, ale kryteria nie są jeszcze spełnione;
- `blocked` — dalsza praca wymaga decyzji, dostępu albo naprawy zależności.

Podaj unit, commit, uruchomione testy, odchylenia od planu i następne polecenie `$dev-docs-review docs/active/<slug> <numer-unitu>`.
