# Review — Unit 1: Bezpieczny baseline repozytorium i CI

- **Data:** 2026-07-24
- **Zakres diffu:** `298f40b92953baa23389c49291bf537c56f9d589..c75a0c8f16f1733433fb3a12ad7cc2e9165660e2`
- **Tryb:** `pełny review`
- **Reviewers:** `correctness_reviewer, security_reviewer, test_reviewer`
- **Gate:** `WYMAGA POPRAWEK`

## Kryteria akceptacji unitu

- Repo hygiene i pełna offline bramka przechodzą bez kluczy API.
- CI wykonuje bramkę oraz audyt zależności.

## Zgodność z planem i zakresem

Review obejmuje wyłącznie 12 plików w commicie Unit 1: przykładowe env,
`.gitignore`, workflow CI/Dependabot, security baseline, pojedynczy hunk
hygiene w `scripts/check_fieldnote.sh`, test hygiene oraz dokumentację zadania.
Nie obejmuje niepowiązanych zmian w brudnym drzewie roboczym. Unit nie zmieniał
interfejsu ani persistence, dlatego nie uruchomiono reviewerów UI/data.

## Skonsolidowane findings

### P1 — blocking

Brak.

### P2 — important

#### P2 — CI nie instaluje zależności API przed uruchomieniem pełnej bramki

- **File:** `.github/workflows/ci.yml:24`
- **Evidence:** job `offline-gate` instaluje tylko root `requirements.txt`, a
  pełna bramka importuje FastAPI i `python-dotenv`, zdefiniowane wyłącznie w
  `fieldnote-api/requirements.txt`.
- **Impact:** świeży runner GitHub Actions nie wykona wymaganej offline bramki.
- **Scenario:** push lub PR na czystym runnerze kończy się `ModuleNotFoundError`
  podczas testów importujących `fieldnote-api/app.py`.
- **Recommendation:** doinstalować zależności `fieldnote-api/requirements.txt`
  w jobie offline-gate albo użyć jednego deterministycznego manifestu.
- **Missing test:** smoke test CI-equivalent w czystym środowisku.

#### P2 — Test sekretów odczytuje worktree, a nie zawartość indeksu

- **File:** `tests/test_repository_hygiene.py:61-68`
- **Evidence:** ścieżki pochodzą z `git ls-files`, lecz `Path.read_text()`
  odczytuje bieżący plik roboczy, nie staged blob.
- **Impact:** bramka może zwrócić PASS, gdy indeks nadal zawiera sekret gotowy
  do commitu.
- **Scenario:** użytkownik stage'uje sekret, usuwa go tylko z worktree bez
  ponownego stage'owania i uruchamia test; test skanuje bezpieczną kopię roboczą.
- **Recommendation:** odczytywać zawartość przez `git show :<path>` lub batch
  `git cat-file`, z jednoznaczną obsługą plików binarnych.
- **Missing test:** regresja z różną zawartością staged i working-tree.

### P3 — non-blocking

Brak.

## Wyniki reviewerów

| Reviewer | Wynik | Findings przyjęte | Findings odrzucone |
|---|---|---:|---:|
| correctness_reviewer | P1, P2 | 2 | 0 |
| security_reviewer | P2 | 1 (zduplikowane P2) | 0 |
| test_reviewer | P2 | 1 (zduplikowane P2) | 0 |

Findings correctness o severity P1 dla CI znormalizowano do P2: jest to
istotnie niespełnione kryterium CI, ale nie luka, utrata danych ani złamany
główny flow aplikacji.

## Testy i weryfikacja

| Kontrola | Wynik | Dowód |
|---|---|---|
| `python3 -m unittest tests/test_repository_hygiene.py` | PASS | 2 testy, ponowione w review |
| `bash scripts/check_fieldnote.sh` | PASS | backend, fixture E2E, frontend typecheck/test/build; bez live provider calls |
| Analiza deklaracji zależności CI | FAIL dla czystego runnera | root `requirements.txt` nie zawiera FastAPI ani python-dotenv |

## Bezpieczeństwo

Minimalne uprawnienia workflow (`contents: read`), brak sekretów w workflow i
przykładowych env oraz brak `pull_request_target` są zgodne z baseline. P2
dotyczą skuteczności egzekwowania tej ochrony w CI i przy staged content.

## Odchylenia od planu

Brak odchyleń funkcjonalnych. CI nie spełnia jeszcze własnego kryterium na
czystym runnerze.

## Kontrole operatora

Pozostają niewykonane: prywatne repo GitHub oraz rotacja ewentualnie ujawnionych
kluczy. Review ich nie oznacza jako ukończonych.

## Decyzja gate

**WYMAGA POPRAWEK** — 0 P1, 2 P2, 0 P3. Review nie jest zakończone do czasu
naprawy obu P2 i ograniczonego re-review.

## Rekomendowany następny krok

`$dev-docs-execute docs/active/fieldnote-stroller-mvp 1` — naprawić wyłącznie
zaakceptowane P2, dodać ich regresje, a następnie wykonać ograniczony
`$dev-docs-review docs/active/fieldnote-stroller-mvp 1`.
