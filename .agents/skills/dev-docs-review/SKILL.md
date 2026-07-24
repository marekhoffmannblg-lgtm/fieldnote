---
name: dev-docs-review
description: "Przegląda wykonany Implementation Unit za pomocą niezależnych, odczytowych subagentów do correctness, bezpieczeństwa i testów, konsoliduje findings oraz zapisuje gate w docs/active. Użyj po dev-docs-execute i do re-review poprawek; nie używaj do implementowania zmian."
---

# Dev Docs Review

Przeprowadź niezależny review jednego wykonanego unitu. Nie edytuj kodu aplikacji i nie naprawiaj findings w tym samym przebiegu.

## 1. Ustal zakres

1. Ustal katalog aktywnego zadania i numer unitu. Gdy numer nie został podany, wybierz ostatni unit oznaczony jako wykonany, ale nieprzejrzany.
2. Przeczytaj w tej kolejności:
   - `<slug>-kontekst.md`;
   - `<slug>-plan.md`;
   - `<slug>-zadania.md`;
   - ostatni raport review, gdy wykonujesz re-review.
3. Ustal kryteria akceptacji unitu, commity, bazę porównania oraz dokładny diff.
4. Zbierz wspólny pakiet review:
   - aktywny katalog zadania;
   - identyfikator unitu i kryteria akceptacji;
   - base ref i zakres diffu;
   - listę zmienionych plików;
   - istotne decyzje z kontekstu;
   - komendy i wyniki testów zgłoszone przez executora.
5. Przy re-review ogranicz zakres do poprawek ostatnich zaakceptowanych findings P1/P2 oraz ich testów regresyjnych.

## 2. Uruchom subagentów

### Fala obowiązkowa

Uruchom równolegle trzech subagentów w trybie tylko do odczytu i przekaż każdemu identyczny pakiet review:

1. `correctness_reviewer` — poprawność, regresje, stany, współbieżność, idempotencja i fałszywy sukces;
2. `security_reviewer` — auth, uprawnienia, RLS, sekrety, zewnętrzne treści, storage i deployment;
3. `test_reviewer` — pokrycie kryteriów akceptacji, testy regresyjne, failure paths i deterministyczność.

Każdy subagent ma analizować wyłącznie przypisany obszar. Nie może edytować plików, wykonywać commitów, aktualizować dokumentów zadania ani naprawiać własnych findings.

### Fala warunkowa

Po zakończeniu fali obowiązkowej uruchom dodatkowych subagentów tylko wtedy, gdy diff tego wymaga:

- `ui_reviewer` — gdy zmieniono interfejs, komponenty React, routing, formularze, dostępność lub stany ładowania/błędów;
- `data_reviewer` — gdy zmieniono migracje, modele, repozytoria, import, scoring, provenance, kolejkę albo worker.

Uruchom wymaganych reviewerów warunkowych równolegle. Nie uruchamiaj ich dla zmian, których ich zakres nie dotyczy.

### Fallback

Gdy subagenci są niedostępni, wykonaj te same przeglądy kolejno w głównym wątku. W raporcie jawnie zapisz `single-agent fallback`. Nie pomijaj żadnej obowiązkowej perspektywy.

## 3. Format wyniku subagentów

Wymagaj od każdego subagenta jednego z dwóch wyników:

- `PASS` — brak obronnych findings w przypisanym zakresie;
- findings w formacie:

```markdown
### P1|P2|P3 — krótki tytuł

- File: `path:line` lub symbol
- Evidence: konkretne zachowanie widoczne w kodzie lub diffie
- Impact: realny wpływ na użytkownika, dane lub system
- Scenario: minimalny sposób wystąpienia problemu
- Recommendation: kierunek najmniejszej poprawki
- Missing test: scenariusz regresyjny, gdy dotyczy
```

Nie przyjmuj uwag stylistycznych, ogólnych zaleceń ani problemów bez wskazania dowodu i scenariusza.

## 4. Zweryfikuj i skonsoliduj

Po otrzymaniu wszystkich wyników:

1. Zweryfikuj każde finding bezpośrednio w repozytorium.
2. Odrzuć findings spekulacyjne, niezgodne z zakresem lub bez odtwarzalnego scenariusza.
3. Scal duplikaty i zachowaj najmocniejszy dowód.
4. Znormalizuj severity:
   - **P1 blocking** — luka bezpieczeństwa, utrata danych, złamany główny flow lub fałszywy sukces;
   - **P2 important** — realna regresja, niespełnione kryterium albo brak testu dla istotnego failure path;
   - **P3 non-blocking** — konkretne ryzyko utrzymaniowe lub pomocniczy brak testu, który nie blokuje unitu.
5. Uruchom automatyczne komendy weryfikacyjne przypisane do unitu. Nie oznaczaj ręcznych kontroli operatora jako wykonanych.
6. Zapisz jeden raport `review-unit-<N>.md` według `references/review-template.md`.
7. Dodaj zaakceptowane P1 i P2 jako checkboxy w sekcji `Do poprawy po review` pliku `<slug>-zadania.md`.
8. W `<slug>-kontekst.md` zapisz zakres review, użytych subagentów, wyniki komend, liczniki findings oraz decyzję gate.

## 5. Gate i następny krok

- P1 obecne: `BLOKUJE`.
- Bez P1, ale z P2: `WYMAGA POPRAWEK`.
- Tylko P3 lub brak findings: `GOTOWE DO KONTYNUACJI`.

Nie oznaczaj review jako zakończone, dopóki pozostaje zaakceptowane P1 lub P2.

Po review z P1/P2 wskaż uruchomienie `$dev-docs-execute` dla tego samego unitu i wyłącznie zaakceptowanych findings. Po poprawkach wskaż ponowne `$dev-docs-review` ograniczone do re-review.

Na końcu podaj ścieżkę raportu, użytych reviewerów, liczniki P1/P2/P3, wynik testów, gate i jeden następny krok.
