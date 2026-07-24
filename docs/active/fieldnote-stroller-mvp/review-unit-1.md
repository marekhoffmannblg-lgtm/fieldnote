# Review — Unit 1: Bezpieczny baseline repozytorium i CI

- **Data:** 2026-07-24
- **Zakres diffu:** `a5454f499cf9a8e3aa72ca96748771cc25e54107..staged` (wyłącznie naprawa ostatniego P2 fixture'u)
- **Tryb:** `re-review`
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer`
- **Gate:** `GOTOWE DO KONTYNUACJI`

## Kryteria akceptacji unitu

- Repo hygiene i pełna offline bramka przechodzą bez kluczy API.
- CI wykonuje bramkę oraz audyt zależności.

## Zgodność z planem i zakresem

Re-review obejmuje wyłącznie poprawki poprzednio zaakceptowanych P2 w
`.github/workflows/ci.yml` i `tests/test_repository_hygiene.py`, wraz z ich
regresjami. Nie obejmuje dokumentacji ani niepowiązanych zmian w brudnym drzewie
roboczym. Unit nie zmieniał interfejsu ani persistence, dlatego nie uruchomiono
reviewerów UI/data.

## Skonsolidowane findings

### P1 — blocking

Brak.

### P2 — important

#### Zamknięte P2 — CI instaluje zależności API przed uruchomieniem pełnej bramki

- **File:** `.github/workflows/ci.yml:24`
- **Evidence:** job `offline-gate` instaluje tylko root `requirements.txt`, a
  pełna bramka importuje FastAPI i `python-dotenv`, zdefiniowane wyłącznie w
  `fieldnote-api/requirements.txt`. Poprawka instaluje oba pliki requirements,
  a regresja sprawdza kontrakt workflow.
- **Status:** zamknięte w `a5454f4`.

#### Zamknięte P2 — Test sekretów odczytuje worktree, a nie zawartość indeksu

- **File:** `tests/test_repository_hygiene.py:61-68`
- **Evidence:** ścieżki pochodzą z `git ls-files`, lecz `Path.read_text()`
  odczytuje bieżący plik roboczy, nie staged blob. Poprawka odczytuje
  `git show :<path>` i ma regresję staged/worktree.
- **Status:** zamknięte w `a5454f4`.

#### Zamknięte P2 — Fixture regresji jest wykrywany jako sekret we własnym pliku testowym

- **File:** `tests/test_repository_hygiene.py:88`
- **Evidence:** fixture zapisywał literal zaczynający się od `sk-`, który
  pasuje do `SECRET_PATTERNS`; po commicie skan indeksu wykrywa sam plik testu.
- **Resolution:** fixture buduje token z fragmentów; śledzony test nie zawiera
  ciągu pasującego do skanera, ale runtime staged blob w tymczasowym repo nadal
  jest wykrywany.
- **Status:** zamknięte po ograniczonym re-review.

### P3 — non-blocking

Brak.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | PASS | 0 | 0 |
| security_reviewer | PASS | 0 | 0 |
| test_reviewer | PASS | 0 | 0 |

Finalny ograniczony re-review objął wyłącznie poprawkę fixture'u. Wszystkie
trzy perspektywy zwróciły PASS; wszystkie poprzednie P2 są zamknięte.

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| `python3 -m unittest tests/test_repository_hygiene.py` | PASS | 4 testy na staged poprawce |
| `bash scripts/check_fieldnote.sh` | PASS | pełna offline bramka, bez Firecrawl/OpenAI |
| Analiza deklaracji zależności CI | PASS | offline-gate instaluje root i `fieldnote-api/requirements.txt` |

## Bezpieczeństwo

Minimalne uprawnienia workflow (`contents: read`), brak sekretów w workflow i
przykładowych env oraz brak `pull_request_target` są zgodne z baseline.

## Odchylenia od planu

Brak odchyleń funkcjonalnych.

## Kontrole operatora

Pozostają niewykonane: prywatne repo GitHub oraz rotacja ewentualnie ujawnionych
kluczy. Review ich nie oznacza jako ukończonych.

## Decyzja gate

**GOTOWE DO KONTYNUACJI** — 0 P1, 0 P2, 0 P3. Review Unit 1 jest zakończone.

## Rekomendowany następny krok

W osobnym uruchomieniu można wykonać `$dev-docs-execute docs/active/fieldnote-stroller-mvp 2`.
