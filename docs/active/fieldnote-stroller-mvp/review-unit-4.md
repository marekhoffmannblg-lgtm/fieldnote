# Review Unit 4 — Logowanie, role i administracja kontami

## Stan review

Pierwszy review implementacji Unit 4 wykazał dwa P1 i P2: mutujące/kosztowe
trasy API nie miały centralnej polityki ról, endpoint zmiany hasła mógł zdjąć
flagę `must_change_password` bez zmiany hasła, a testy nie wykonywały macierzy
HTTP dla ról.

Pierwsza poprawka związała zmianę hasła z serwerowym Supabase Auth i dodała
wymaganie sesji dla `/api/*` w trybie Supabase. Ograniczony re-review wykazał,
że viewer nadal mógł wywoływać mutujące endpointy oraz że macierz HTTP nadal
nie była wykonawcza.

## Poprawka oczekująca re-review

- `fieldnote-api/app.py`: middleware odrzuca `POST`, `PUT`, `PATCH` i `DELETE`
  dla viewer; odczyt pozostaje dostępny dla viewer, analyst i admin.
- `tests/test_auth_roles.py`: `TestClient` sprawdza 401 dla anon, odczyt dla
  wszystkich ról, 403 dla wymuszonej zmiany hasła oraz 403 dla mutacji viewer.
- `fieldnote-api/requirements.txt`: dodano `httpx`, wymagane przez TestClient.

## Weryfikacja executora

- `python3 -m unittest tests/test_auth_roles.py tests/test_fieldnote_api_contracts.py`: PASS (27).
- `bash scripts/check_fieldnote.sh`: PASS.
- `git diff --check`: PASS.

Wynik końcowy pozostaje **PENDING RE-REVIEW**. Unit 4 może zostać oznaczony
jako ukończony wyłącznie po PASS bez P1/P2; Unit 5 nie został rozpoczęty.
