# FIELDNOTE Stroller MVP — plan wykonawczy

- **Branch:** `main` (brudne drzewo robocze; branch nie został zmieniony)
- **Ostatnia aktualizacja:** 2026-07-28

## Źródła

- Requirements: `docs/brainstorms/2026-07-23-fieldnote-stroller-mvp-requirements.md`
- Plan techniczny: `docs/plans/2026-07-23-001-feat-fieldnote-stroller-mvp-plan.md`

## Cel i granice

Domknąć wieloużytkownikowe MVP benchmarku wózków Lionelo przez stopniowe opakowanie obecnego pipeline'u React/FastAPI/Python w Supabase, worker i wdrożenie Render. Zakres obejmuje wyłącznie obecny katalog wózków i konkurentów. Nie dodawać kolejnych kategorii, marek ani funkcji poza zatwierdzonym planem.

## Fazy wykonawcze

### Faza 0 — Unit 1: Bezpieczny baseline repozytorium i CI

- Status: `completed` (review PASS)
- Zależności: brak
- Kryterium ukończenia: repo hygiene i pełna offline bramka przechodzą bez kluczy API; CI wykonuje bramkę i audyt zależności.

### Faza 0 — Unit 1.5: Repository cleanup

- Status: `completed` (bezpieczny zakres; oczekuje na review)
- Zależności: Unit 1
- Kryterium ukończenia: root ma udokumentowaną klasyfikację; usunięte są wyłącznie odtwarzalne cache/środowiska, a pakiety diagnostyczne są poza aktywnym kodem bez relokacji ścieżek runtime.

### Faza 1 — Unit 2: Supabase schema, Auth, Storage i RLS

- Status: `completed` (review PASS)
- Zależności: Unit 1
- Kryterium ukończenia: migracje, idempotentny seed oraz testy ról/RLS działają dla anon, viewer, analyst i admin.

### Faza 1 — Unit 3: Repozytoria Supabase i selektywna migracja

- Status: `completed` (review PASS)
- Zależności: Unit 2
- Kryterium ukończenia: 34 produkty Lionelo i prawidłowe provenance są migrowane idempotentnie; legacy pozostaje read-only do porównania.

### Faza 1 — Unit 4: Logowanie, role i administracja kontami

- Status: `completed` (review PASS)
- Zależności: Unit 2, Unit 3
- Kryterium ukończenia: JWT, macierz ról oraz wymuszona zmiana pierwszego hasła chronią API i UI.

### Faza 2 — Unit 5: Kolejka PostgreSQL i worker z dwoma slotami

- Status: `completed` (implementacja i weryfikacja; oczekuje na review)
- Zależności: Unit 3, Unit 4
- Kryterium ukończenia: trwałe joby, lease, maksymalnie dwa różne produkty i brak podwójnego uruchomienia tego samego produktu.

### Faza 2 — Unit 6: Przyrostowe commitowanie i przeliczanie

- Status: `pending`
- Zależności: Unit 3, Unit 5
- Kryterium ukończenia: research produktu zmienia wyłącznie jego scope; pełna przebudowa jest osobną, serializowaną akcją administratora.

### Faza 3 — Unit 7: Wspólny Firecrawl i aktualny katalog konkurencji

- Status: `pending`
- Zależności: Unit 5, Unit 6
- Kryterium ukończenia: wszystkie adaptery używają wspólnego klienta i kontraktu provenance; aktualny katalog nie ma niejawnych placeholderów ani niesklasyfikowanych realnych rekordów.

### Faza 3 — Unit 8: Audyt atrybutów i względny scoring wózków

- Status: `pending`
- Zależności: Unit 3, Unit 7
- Kryterium ukończenia: raport obejmuje 21 pól, scoring jest deterministyczny w czterech segmentach, a cena nie wpływa na wynik użytkowy.

### Faza 4 — Unit 9: UI produkcyjne i import administratora

- Status: `pending`
- Zależności: Unit 4–8
- Kryterium ukończenia: UI działa wyłącznie przez API, import XLSX ma preview/commit, a role ograniczają akcje.

### Faza 5 — Unit 10: Render staging/production i security gate

- Status: `pending`
- Zależności: Unit 1–9
- Kryterium ukończenia: oddzielne usługi frontend/API/worker i środowiska przechodzą testy deploymentu oraz security gate.

### Faza 5 — Unit 11: Zamknięcie danych MVP i raport

- Status: `pending`
- Zależności: Unit 1–10
- Kryterium ukończenia: audit MVP przechodzi dla 34 produktów Lionelo, aktualnych konkurentów, benchmarków i provenance.

## Ryzyka i kolejność

- Nie rozpoczynać jednostki przed jej zależnościami ani nie rozszerzać katalogu poza istniejące wózki.
- Płatne Firecrawl/OpenAI są wyłączone z testów; live runy mogą być wykonywane wyłącznie w kontrolowanych etapach wskazanych przez plan.
- Migracje, Auth, RLS i Storage wymagają niezależnego security review przed kolejnym unitem.
- Brudne drzewo robocze oznacza, że każdy unit musi stage'ować wyłącznie własne pliki — bez `git add .`.

## Odchylenia od planu technicznego

- Unit 5 zachowuje legacy endpointy i manifesty jako kompatybilny interfejs diagnostyczny. Nowy ekran researchu oraz lista uruchomień korzystają z `/api/jobs`; źródłem prawdy dla tych jobów jest PostgreSQL. Przyrostowe przeliczanie pozostało wyłącznie w Unit 6.
