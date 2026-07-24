---
name: supabase-guidelines
description: "Stosuje bezpieczne wzorce Supabase dla PostgreSQL, Auth, Storage, migracji i RLS w aplikacji z FastAPI i React. Użyj przy modelu danych, logowaniu, rolach, politykach, bucketach i migracji z plików."
---

# Supabase Guidelines

## Architektura

- PostgreSQL jest źródłem prawdy; lokalne JSON/CSV są wyłącznie importem, fixture lub archiwum.
- Zmieniaj schemat wyłącznie migracjami w repozytorium.
- React korzysta z anon key i ograniczonego API; service-role pozostaje w FastAPI/workerze.
- FastAPI weryfikuje sesję i role przed operacjami uprzywilejowanymi.

## RLS i role

- Włącz RLS na każdej tabeli dostępnej przez Supabase API.
- Wszyscy zalogowani mogą czytać katalog i benchmarki.
- Odbiorca nie edytuje; analityk uruchamia research i edytuje dane; administrator zarządza użytkownikami i konfiguracją.
- Nie ufaj danym roli przesłanym przez klienta.
- Testuj polityki dla każdej roli i dla użytkownika niezalogowanego.

## Dane i storage

- Oddziel encje produktu, modelu+konfiguracji, źródła, evidence, wartości atrybutu, ceny, runu i snapshotu.
- Surowy wynik Firecrawl zapisuj w prywatnym bucketcie; w bazie przechowuj metadane i ścieżkę.
- Używaj idempotentnych upsertów z jednoznacznymi kluczami biznesowymi.
- Snapshot twórz tylko dla istotnej zmiany, a run zapisuj zawsze.
- Migrację z plików wykonuj selektywnie i z raportem odrzuconych rekordów.

Przy auth, JWT, RLS i Storage sprawdzaj aktualne oficjalne docs Supabase przed implementacją.
