# Review — Unit 4: Logowanie, role i administracja kontami

- **Data:** 2026-07-28
- **Zakres diffu:** `cd9ba46^..cd9ba46`
- **Tryb:** ograniczony re-review
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer, ui_reviewer`
- **Gate:** `WYMAGA POPRAWEK`

## Kryteria akceptacji unitu

JWT, macierz ról i wymuszona pierwsza zmiana hasła chronią API i UI. Użytkownik
może opuścić ekran pierwszej zmiany hasła wyłącznie po potwierdzonej przez API
zmianie hasła i zdjęciu flagi.

## Zgodność z planem i zakresem

Zakres ograniczono do naprawy P1 z poprzedniego raportu: przekazania hasła do
serwerowego endpointu, odświeżenia profilu i testu regresyjnego. Poprzedni P1
jest zamknięty: UI nie wywołuje `supabase.auth.updateUser()` i przesyła hasło
przez `apiRequest` do FastAPI. Unit 5 nie został rozpoczęty.

## Skonsolidowane findings

### P1 — blocking

Brak.

### P2 — important: brak literalnego potwierdzenia odpowiedzi zmiany hasła

- **File:** `fieldnote-frontend/src/auth/passwordChange.ts:16`
- **Evidence:** warunek `if (response.must_change_password)` odrzuca tylko wartości truthy. Odpowiedź 200 `{}` lub `{ "must_change_password": null }` przechodzi do `refreshProfile()` mimo braku kontraktowego potwierdzenia.
- **Impact:** UI może zakończyć submit bez jawnego potwierdzenia, że serwer zdjął flagę; przy niepełnej odpowiedzi użytkownik wraca na ten sam ekran bez komunikatu błędu.
- **Scenario:** endpoint lub pośrednik zwraca 200 z pustym/niepełnym JSON; helper kończy się sukcesem zamiast zgłosić błąd.
- **Recommendation:** wymagaj `response.must_change_password === false` przed `refreshProfile()`; w przeciwnym razie zgłoś błąd.
- **Missing test:** `{}` i `null` nie wywołują `refreshProfile()`; `{must_change_password: true}` również jest odrzucone.

### P3 — non-blocking

Brak.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | PASS | 0 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | P2 | 1 | 0 |
| ui_reviewer | PASS | 0 | 0 |

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| Frontend tests | PASS | `pnpm test` — 12 testów |
| Frontend typecheck | PASS | `pnpm run typecheck` |
| Pełna offline bramka | PASS | `bash scripts/check_fieldnote.sh` |
| Spójność diffu | PASS | `git diff --check cd9ba46^ cd9ba46` |

## Bezpieczeństwo

Security reviewer potwierdził, że nowy flow wysyła hasło tylko przez
autoryzowany backend i nie omija serwerowej kolejności operacji. Nie znaleziono
sekretów ani dodatkowych problemów uprawnień.

## Odchylenia od planu

Brak. To poprawka tylko P1 Unit 4; Unit 5 nie został rozpoczęty.

## Kontrole operatora

Browser flow z prawdziwym projektem Supabase pozostaje niewykonaną kontrolą
ręczną po przejściu bramki automatycznej.

## Decyzja gate

**WYMAGA POPRAWEK** — 0 P1, 1 P2, 0 P3. Unit 4 nie może otrzymać PASS,
dopóki helper nie wymaga literalnego potwierdzenia odpowiedzi.

## Stan po naprawie

Poprawka oczekuje ograniczonego re-review: helper wymaga teraz literalnego
`must_change_password === false`. Test regresyjny pokrywa odpowiedzi `{}`,
`null` i `true`, które odrzucają Promise bez wywołania `refreshProfile()`.
Frontend tests (15), typecheck/build, pełna offline bramka oraz
`git diff --check` przeszły. Wynik tego raportu pozostaje `WYMAGA POPRAWEK`
aż do niezależnego re-review wyłącznie P2.

## Rekomendowany następny krok

`$dev-docs-review docs/active/fieldnote-stroller-mvp 4` — wykonaj ograniczony
re-review wyłącznie poprawki P2 i nie rozpoczynaj Unit 5.
