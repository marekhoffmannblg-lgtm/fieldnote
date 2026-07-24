---
name: security-review
description: "Audytuje bezpieczeństwo aplikacji React/FastAPI/Supabase oraz pipeline Firecrawl. Użyj przed wdrożeniem, przy zmianach auth, RLS, uploadów, URL-i, sekretów, storage lub publicznych endpointów."
---

# Security Review

Traktuj bezpieczeństwo jako bramkę przed publikacją.

## Sprawdź obowiązkowo

- sekrety i klucze API nigdy nie trafiają do frontendu, logów ani repo;
- rejestracja publiczna jest wyłączona, konta tworzy administrator;
- token użytkownika jest weryfikowany po stronie FastAPI;
- role są egzekwowane w backendzie, nie tylko w UI;
- RLS obejmuje wszystkie tabele i buckety dostępne przez klienta;
- service-role działa wyłącznie w backendzie/workerze;
- upload XLSX ma limity rozmiaru, typu i bezpieczny parser;
- URL-e do Firecrawl są walidowane, aby ograniczyć SSRF i niechciane domeny;
- endpointy researchu mają limity, idempotencję i ochronę przed duplikacją;
- logi i snapshoty nie zawierają haseł, tokenów ani prywatnych nagłówków;
- staging i produkcja mają oddzielne projekty, klucze i storage.

Dla zmiennych w czasie zachowań Supabase/Auth sprawdzaj aktualną oficjalną dokumentację. Raportuj findings z wagą, dowodem i testem regresyjnym.
