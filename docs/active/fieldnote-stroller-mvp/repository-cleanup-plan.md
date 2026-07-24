# Unit 1.5 — Repository cleanup

- **Data audytu:** 2026-07-24
- **Zakres:** wyłącznie root i lokalne artefakty; bez relokacji kodu ani Unit 2.
- **Stan:** bezpieczny zakres wykonany; relokacje kodu pozostają odroczone.

## Ustalenia o runtime

Aktywne są dwa surface'y aplikacji. `fieldnote-api/` i
`fieldnote-frontend/` są używane przez CI oraz `scripts/check_fieldnote.sh`.
Równolegle rootowy Streamlit jest nadal wspierany: `app.py` importuje `ui/`,
strony w `pages/` używają `services/`, a `services/pipeline_runner.py` wywołuje
kanoniczny `scripts/run_model_research_pipeline.py`. `input/`, `output/` i
`data/` mają potwierdzone reader/writer w API, Streamlit, skryptach i testach.

## Audyt rootu

| Element rootu | Klasyfikacja | Obecna funkcja | Decyzja |
|---|---|---|---|
| `.agents/`, `.codex/`, `.github/`, `.streamlit/`, `AGENTS.md`, `.env.example`, `.gitignore`, `requirements.txt` | konfiguracja | workflow Codex, CI, Streamlit, env | keep |
| `.git/` | niepewne — wymaga zachowania | historia i indeks Git | keep |
| `.codex-starter-backup/` | niepewne — wymaga zachowania | backup startera | keep |
| `.DS_Store` | kandydat do usunięcia | metadane Finder | delete |
| `.pnpm-store/`, `.vite/`, `.venv/`, `__pycache__/` | wygenerowany artefakt | cache i local env rootowego Python/Streamlit | delete |
| `FIELDNOTE_APP_CURRENT_STATE.zip`, `codex_ai_test_check.zip`, `fieldnote_diagnostic_bundle.zip`, `projekt_*.zip` | wygenerowany artefakt | lokalne eksporty/diagnostyka | move do archive |
| `MVP_AUDIT.md`, `README.md` | dokumentacja | stan produktu i instrukcje | keep |
| `app.py`, `pages/`, `services/`, `src/`, `ui/` | aktywna część aplikacji / legacy | Streamlit aktywny; `src/` prawdopodobnie legacy | keep, nie przenosić |
| `data/` | fixture lub dane wejściowe | lokalny katalog/specyfikacje importu | keep |
| `docs/` | dokumentacja | plan, audyty, aktywne zadanie | keep |
| `fieldnote-api/` | aktywna część aplikacji | FastAPI i run coordinator | keep; czyścić tylko `.venv/`/cache |
| `fieldnote-frontend/` | aktywna część aplikacji | Vite/React, CI i build | keep; czyścić tylko `node_modules*`, `dist/` |
| `fieldnote_codex_next_steps/`, `fieldnote_codex_prompts/` | legacy / dokumentacja historyczna | brak referencji runtime | keep; późniejsza decyzja o archive |
| `fixtures/` | fixture lub dane wejściowe | demo i E2E offline | keep |
| `input/` | fixture lub dane wejściowe | raw listings, snapshots i kolejki | keep ścieżkę i zawartość |
| `output/` | wygenerowany artefakt / niepewne | pipeline state/run history oraz pakiety diagnostyczne | keep ścieżkę; move tylko ZIP-y |
| `project_files.txt` | kandydat do usunięcia | inventory bez referencji runtime | move do tracked archive |
| `scripts/`, `tests/` | aktywna część aplikacji | kanoniczny pipeline i offline gate | keep |

## Struktura docelowa

```text
fieldnote-api/  fieldnote-frontend/  scripts/  tests/
app.py pages/ services/ src/ ui/     # zachować do oddzielnego audytu migracji
fixtures/ data/ input/ output/       # kanoniczne ścieżki danych
docs/ .github/ .agents/ .codex/
archive/repository-cleanup/2026-07-24/
  root-diagnostics/ output-diagnostics/ project_files.txt
```

## Dokładne listy keep/move/delete

### Wykonać teraz

| Operacja | Target | Ryzyko i ochrona |
|---|---|---|
| delete | `.venv/`, `fieldnote-api/.venv/`, `.pnpm-store/`, `.vite/`, wszystkie `__pycache__/`, `fieldnote-frontend/node_modules/`, `fieldnote-frontend/node_modules 2/`, `fieldnote-frontend/dist/`, wszystkie `.DS_Store` | odtwarzalne; lokalny start wymaga ponownej instalacji |
| move | sześć rootowych ZIP-ów do `archive/repository-cleanup/2026-07-24/root-diagnostics/` | tylko manual recovery, brak referencji runtime |
| move | ZIP-y z `output/` do `archive/repository-cleanup/2026-07-24/output-diagnostics/` | tylko pakiety review/test; nie ruszać JSON/CSV/run state |
| move | `project_files.txt` do `archive/repository-cleanup/2026-07-24/project_files.txt` | zachować tracked historię inventory |
| ignore | ZIP-y w obu podkatalogach archive oraz `fieldnote-frontend/node_modules 2/` | artefakty nie mogą wejść do indeksu |

### Keep / odroczyć

| Target | Powód / warunek ruchu |
|---|---|
| `src/` | wymagany audyt importów i CLI |
| `app.py`, `pages/`, `services/`, `ui/` | aktywny Streamlit; potrzebny oddzielny plan migracji |
| `fieldnote-api/`, `fieldnote-frontend/`, `scripts/`, `tests/` | ścieżka CI/runtime |
| `data/`, `input/`, `output/` | pełna mapa reader/writer i migration plan |
| `fieldnote_codex_*`, `.codex-starter-backup/` | decyzja retencji właściciela |

## Importy i ścieżki

W bezpiecznej części: **brak zmian importów i ścieżek**. Przyszła relokacja
`src/` wymaga mapy importów; relokacja Streamlit wymaga aktualizacji README,
`.streamlit`, `app.py`, `pages/`, `ui/`, `services/` i testów.

## Weryfikacja braku regresji

1. Przed usunięciem: `bash scripts/check_fieldnote.sh`.
2. Po usunięciu: `find` potwierdza brak wyłącznie wskazanych cache/env.
3. `python3 -m unittest tests/test_repository_hygiene.py` i `git ls-files`
   nie znajdują cache, env ani archiwów ZIP w indeksie.
4. Po przyszłych relokacjach: pełny offline gate, import smoke tests,
   frontend typecheck/test/build oraz ręczny smoke test Streamlit/API.

## Wynik wykonania bezpiecznego zakresu

- Usunięto root/API virtualenv, cache pnpm/Vite, oba katalogi `node_modules`,
  `dist`, wszystkie `__pycache__` oraz `.DS_Store`.
- Przeniesiono 6 ZIP-ów rootowych i 25 ZIP-ów z `output/` do lokalnego
  `archive/repository-cleanup/2026-07-24/`; `project_files.txt` jest w tym
  samym archiwum jako tracked historyczny inventory.
- Nie zmieniono ani nie przeniesiono `src/`, `services/`, `fieldnote-api/`,
  `app.py`, `pages/`, `ui/`, `input/`, `output/` (poza ZIP-ami) ani `data/`.
- Pełna offline bramka przeszła przed usunięciem środowisk. Po cleanupie
  `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_repository_hygiene.py`
  przeszło (4 testy), nie odtwarzając cache.
