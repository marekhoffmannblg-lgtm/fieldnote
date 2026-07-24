# Instrukcje projektu dla Codexa

## Najpierw przeczytaj

1. `docs/CONCEPTS.md`.
2. Pasujący dokument w `docs/brainstorms/`.
3. Źródłowy plan w `docs/plans/`.
4. Gdy istnieje aktywne zadanie: jego `*-plan.md`, `*-kontekst.md`, `*-zadania.md` i ostatni raport review.
5. `MVP_AUDIT.md` i repozytoryjny `README.md`, gdy istnieją.

## Kierunek architektury

Rozwijaj istniejący projekt przyrostowo. Nie przepisuj go od zera.

Docelowy układ:

- React/Vite: frontend;
- FastAPI: API i autoryzacja;
- osobny worker Python: zadania Firecrawl/OpenAI;
- Supabase: PostgreSQL, Auth i Storage;
- Render: frontend, API i worker.

Zachowaj działający pipeline, provenance, evidence, retry, quality gate i historię runów. Najpierw opakuj istniejące skrypty nowymi interfejsami, potem refaktoryzuj.

## Scope MVP

- Dokończ wszystkie wózki i konkurentów, którzy już istnieją w projekcie.
- Benchmark wewnętrzny obejmuje cały katalog Lionelo.
- Benchmark zewnętrzny używa obecnych marek i modeli konkurencji.
- Jednostka benchmarku: `model + konfiguracja`; kolory są ignorowane.
- Cena jest osobna od rankingu użytkowego.
- Brak danych nie daje zera; obniża kompletność.
- Recenzje, social media, automatyczne rekomendacje strategiczne i kolejne kategorie są poza MVP.

## Zasady pracy

- Dla pracy wieloetapowej używaj `docs/active/` jako trwałego źródła stanu.
- Wykonuj dokładnie jeden Implementation Unit na uruchomienie `dev-docs-execute`.
- Pytaj użytkownika tylko o prawdziwy bloker produktowy; wybory techniczne rozwiązuj najprostszym bezpiecznym wariantem.
- Nie używaj płatnych API w testach; korzystaj z fixtures.
- Nie przechowuj sekretów w repo, frontendzie, logach ani snapshotach.
- Nie osłabiaj testów, typowania, walidacji, RLS ani limitów kosztu.
- Nie zakładaj, że lokalny dysk Rendera jest trwały.
- Nie wykonuj globalnego przeliczenia katalogu po researchu jednego modelu.
- Nie wdrażaj publicznie przed przejściem security gate.
- Nie usuwaj starych danych bez zachowania archiwum lub migracji.
- Nie używaj `git add .`; stage'uj tylko pliki bieżącego unitu.

## Preferowany workflow

1. `grill-me` tylko dla nierozstrzygniętych decyzji produktowych.
2. `dev-plan` tworzy lub aktualizuje techniczny plan.
3. `dev-docs` tworzy trwałe zadanie w `docs/active/`.
4. `dev-docs-execute` wykonuje jeden unit.
5. `dev-docs-review` niezależnie sprawdza unit.
6. `dev-docs-update` utrwala stan przed kompaktowaniem lub zmianą sesji.
7. `dev-docs-complete` archiwizuje zadanie po pełnym zamknięciu.

Subagentów używaj przede wszystkim do eksploracji i niezależnego review. Edycje wykonuj seryjnie.
