# Fieldnote — lokalne uruchamianie i sesja auth

## Cel

Zapewnić jeden powtarzalny start lokalnego Supabase, backendu i frontendu oraz
czytelne zakończenie inicjalizacji sesji, gdy API jest niedostępne.

## Zakres

- health endpoint backendu `/health` oraz istniejący `/api/health`;
- start/stop/status przez `scripts/start_fieldnote_local.sh`, z procesami
  odłączonymi od terminala i jednoznacznym rozpoznaniem własnych procesów;
- timeout dla frontendowego `getSession` i `/api/auth/me`;
- testy kontraktowe i wykonawcza weryfikacja portów.

## Poza zakresem

Unit 8.5, nowe funkcje produktowe, migracje danych, naprawa RLS, Firecrawl,
OpenAI oraz pozostałe findings z audytu.

## Implementation Unit 1 — local runtime gate

Pliki: `scripts/start_fieldnote_local.sh`, `fieldnote-api/app.py`,
`fieldnote-frontend/src/auth/AuthProvider.tsx`, `fieldnote-frontend/src/api/client.ts`,
testy backendu i frontendu oraz dokumentacja aktywnego zadania.

Akceptacja: `scripts/start_fieldnote_local.sh start/status/stop` jest
powtarzalny; `/health`, `/api/health`, frontend i Supabase Auth odpowiadają;
`/api/auth/me` kończy się sukcesem lub błędem w ograniczonym czasie; UI pokazuje
login albo czytelny błąd zamiast nieskończonego loadingu; procesy działają po
zamknięciu terminala.
