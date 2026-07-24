---
name: fastapi-python-guidelines
description: "Stosuje wzorce FastAPI/Python dla API, workerów, usług domenowych, repozytoriów, walidacji Pydantic i testów. Użyj przy backendzie, kolejce researchu i migracji istniejących skryptów."
---

# FastAPI Python Guidelines

## Warstwy

- Router: HTTP, auth, walidacja wejścia i mapowanie odpowiedzi.
- Service: reguły biznesowe i orkiestracja.
- Repository: PostgreSQL/Storage; bez logiki domenowej.
- Pipeline adapter: opakowuje istniejące skrypty bez przepisywania ich naraz.
- Worker: pobiera zadanie, ustawia status, wykonuje pipeline i zapisuje rezultat.

## Reguły

- Pydantic na granicach; nie przekazuj surowych dictów przez cały system.
- Błędy domenowe mapuj centralnie na stabilne kody API.
- Każde zadanie ma idempotency key, status, retry count, koszt i timestamps.
- Ten sam model+konfiguracja nie może mieć dwóch aktywnych researchów.
- Zamykanie karty nie przerywa zadania.
- Nie wykonuj długiego Firecrawl/OpenAI wewnątrz requestu HTTP.
- Maksymalnie dwa zadania równolegle; reszta czeka w PostgreSQL.
- Nie polegaj na lokalnym dysku Rendera jako trwałym storage.
- Testy jednostkowe nie korzystają z sieci ani płatnych API.
- Zachowaj obecne provenance, evidence, quality gate i retry jako kontrakty podczas migracji.

Preferuj małe moduły i jawne zależności. Nie twórz abstrakcji dla przyszłych kategorii przed domknięciem wózków.
