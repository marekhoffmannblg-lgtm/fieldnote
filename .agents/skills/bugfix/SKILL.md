---
name: bugfix
description: "Prowadzi systematyczną naprawę błędu: reprodukcja, znalezienie przyczyny źródłowej, test regresyjny, minimalna poprawka i weryfikacja. Użyj dla zgłoszeń, failing tests i błędów runtime."
---

# Bugfix

Naprawiaj przyczynę, nie objaw.

1. Zbierz oczekiwane i rzeczywiste zachowanie oraz najkrótszą reprodukcję.
2. Prześledź dane od miejsca błędu do źródła. Nie zgaduj na podstawie komunikatu z końca łańcucha.
3. Dodaj test regresyjny lub characterization test, który najpierw ujawnia problem.
4. Wprowadź najmniejszą poprawkę bez szerokiego refaktoru.
5. Sprawdź sąsiednie przypadki: brak danych, retry, duplikaty, częściowy sukces, równoległe zadania i idempotencję.
6. Uruchom test celowany oraz szerszy quality gate.

Dla Firecrawl/OpenAI używaj fixtures. Nie testuj błędu na produkcyjnych danych. Jeśli nie da się odtworzyć, dodaj diagnostykę zamiast losowej poprawki.
