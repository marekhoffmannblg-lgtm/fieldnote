---
name: code-review
description: "Przegląda diff, branch lub wskazane pliki pod kątem realnych regresji, bezpieczeństwa, błędów logicznych i brakujących testów. Użyj przed merge albo po wykonaniu Implementation Unit; domyślnie nie edytuje kodu."
---

# Code Review

Przeglądaj jak właściciel systemu. Domyślnie nie edytuj kodu.

## Przebieg

1. Ustal bazę porównania i zakres diffu.
2. Przeczytaj wymagania, plan oraz ścieżki wywołań dotknięte zmianą.
3. Dla większego diffu uruchom równolegle `reviewer` i `security_reviewer`; użyj `explorer` do mapowania zależności.
4. Zweryfikuj testy i kontrakty API, bazę, kolejkę zadań, statusy oraz propagację błędów.
5. Zgłaszaj wyłącznie problemy mające wpływ na zachowanie, bezpieczeństwo, dane, koszty lub utrzymanie.

## Format odpowiedzi

Najpierw findings, od najwyższej wagi:

- `P0/P1/P2/P3`
- plik i symbol
- konkretne zachowanie lub scenariusz awarii
- dowód z kodu
- najmniejsza sensowna naprawa
- brakujący test

Na końcu podaj: testy przejrzane/uruchomione, ryzyka nieweryfikowalne lokalnie i werdykt `blokuje merge` albo `nie blokuje merge`.

Nie zgłaszaj style-only uwag, chyba że ukrywają błąd.
