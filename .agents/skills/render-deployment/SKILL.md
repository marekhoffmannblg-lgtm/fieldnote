---
name: render-deployment
description: "Przygotowuje bezpieczne wdrożenie aplikacji React, FastAPI i workera Python na Render z Supabase jako bazą i storage. Użyj przy stagingu, produkcji, env, health checks, migracjach i rollbacku."
---

# Render Deployment

## Usługi

- frontend React/Vite jako Static Site;
- FastAPI jako Web Service;
- worker Python jako Background Worker;
- Supabase jako PostgreSQL, Auth i Storage.

## Zasady

- Utrzymuj osobne projekty i sekrety dla stagingu i produkcji.
- Nie przechowuj trwałych danych na dysku Rendera.
- API ma lekki endpoint health, który nie wywołuje Firecrawl/OpenAI.
- Worker i API używają tej samej wersji kodu oraz zgodnego schematu bazy.
- Migracje uruchamiaj jawnie przed przełączeniem ruchu; muszą być wstecznie kompatybilne w okresie rollout.
- Produkcja wdrażana ręcznie po zielonym stagingu; automatyczny deploy może dotyczyć stagingu.
- Zdefiniuj limity czasu, retry i graceful shutdown workera.
- Logi identyfikują run/job, ale nie zawierają sekretów ani pełnych payloadów auth.
- Opisz rollback aplikacji i migracji przed pierwszym publicznym wdrożeniem.

Przed konfiguracją sprawdź aktualne oficjalne dokumenty Render dotyczące Web Services, Static Sites i Background Workers.
