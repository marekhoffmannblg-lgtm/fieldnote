# Review — Unit 4: Logowanie, role i administracja kontami

- **Data:** 2026-07-28
- **Zakres diffu:** `475e04c^..475e04c`
- **Tryb:** re-review
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer`
- **Gate:** `BLOKUJE`

## Kryteria akceptacji unitu

JWT, macierz ról i wymuszona pierwsza zmiana hasła mają chronić API i UI:
anon otrzymuje 401, viewer nie wykonuje mutacji, analyst/admin zachowują
uprawnienia, a użytkownik może zakończyć pierwszy flow zmiany hasła.

## Zgodność z planem i zakresem

Re-review obejmuje centralną politykę ról i macierz HTTP z `475e04c`.
Podczas weryfikacji correctness znaleziono odtwarzalny błąd głównego flow
Unitu 4 bezpośrednio powiązany z poprawianą bramką `must_change_password`.
Nie wykracza on poza kryterium ukończenia unitu.

## Skonsolidowane findings

### P1 — blocking: frontend nie może zakończyć wymuszonej zmiany hasła

- **File:** `fieldnote-frontend/src/auth/AuthProvider.tsx:108`; `fieldnote-api/routers/auth.py:13-17`
- **Evidence:** `changeInitialPassword()` wykonuje `supabase.auth.updateUser({ password })`, potem wywołuje `POST /auth/change-password` bez body. Router wymaga `ChangePasswordRequest.password`, więc FastAPI odpowiada 422 przed `UserService.change_password()`.
- **Impact:** profil zachowuje `must_change_password=true`; użytkownik zostaje na ekranie zmiany hasła mimo pomyślnej zmiany hasła w Supabase.
- **Scenario:** administrator tworzy konto, użytkownik loguje się i ustawia nowe hasło; frontend wykonuje pusty POST, API odpowiada 422, a kolejne logowanie ponownie wymaga zmiany hasła.
- **Recommendation:** przekazuj `password` w JSON do API i usuń bezpośrednie `supabase.auth.updateUser`, aby serwer wykonał najpierw zmianę hasła, a później zdjęcie flagi.
- **Missing test:** mock UI/API lub E2E potwierdzający payload, odpowiedź `must_change_password=false` i przejście z ekranu zmiany hasła do katalogu.

### P2 — important

Brak.

### P3 — non-blocking

Brak.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | P1 | 1 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | PASS | 0 | 0 |

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Focused API | PASS | `fieldnote-api/.venv/bin/python -m unittest tests/test_auth_roles.py tests/test_fieldnote_api_contracts.py` — 27 testów |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` |
| Spójność diffu | PASS | `git diff --check 475e04c^ 475e04c` |

## Bezpieczeństwo

Centralna polityka poprawnie blokuje mutacje viewer; security review nie
wykazał dodatkowego findingu. P1 pozostaje błędem dostępności głównego flow
autoryzacji i blokuje zamknięcie unitu.

## Odchylenia od planu

Brak zmian zakresu. Unit 5 nie został rozpoczęty.

## Kontrole operatora

Browser flow z prawdziwym projektem Supabase pozostaje kontrolą ręczną po
naprawie P1; nie oznaczono go jako wykonanego.

## Decyzja gate

**BLOKUJE** — 1 P1, 0 P2, 0 P3. Unit 4 nie ma PASS i nie może zostać
oznaczony jako ukończony.

## Stan po naprawie

Naprawa została przygotowana w oczekującym commicie: frontend przekazuje
`{password}` do API i nie zmienia już hasła bezpośrednio przez klienta
Supabase. Helper wymaga odpowiedzi `must_change_password=false`, a następnie
odświeża profil. Dodano test payloadu i przejścia flagi profilu. API focused
tests (27), frontend tests (12), typecheck/build, pełna offline bramka i
`git diff --check` przeszły. Wynik tego raportu pozostaje `BLOKUJE` aż do
ograniczonego re-review wyłącznie naprawy P1.

## Rekomendowany następny krok

`$dev-docs-review docs/active/fieldnote-stroller-mvp 4` — wykonaj ograniczony
re-review wyłącznie naprawy P1 i nie rozpoczynaj Unit 5.
