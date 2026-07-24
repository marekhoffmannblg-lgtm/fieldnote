# FIELDNOTE Stroller MVP — kontekst

- **Branch:** `main` (nieprzełączony z powodu brudnego drzewa roboczego)
- **Ostatni commit przed Unit 1:** `298f40b92953baa23389c49291bf537c56f9d589 — docs: initialize fieldnote stroller mvp task`
- **Ostatnia aktualizacja:** 2026-07-24

## Źródła

- Requirements: `docs/brainstorms/2026-07-23-fieldnote-stroller-mvp-requirements.md`
- Plan techniczny: `docs/plans/2026-07-23-001-feat-fieldnote-stroller-mvp-plan.md`

## Obecny stan repozytorium

- Drzewo robocze jest obszernie zmodyfikowane i zawiera zarówno zmienione pliki śledzone, jak i nieśledzone artefakty oraz kod projektu. Nie należy go resetować, czyścić ani przełączać brancha podczas inicjalizacji.
- Istnieje lokalny pipeline Python, FastAPI, frontend React/Vite, provenance, quality gate, retry i historia runów. Kanoniczny entrypoint researchu pozostaje `scripts/run_model_research_pipeline.py`.
- Repozytoryjny starter Codex v2 jest zainstalowany. Wprowadza workflow `dev-docs`; jego konfiguracja nie wykonuje pracy aplikacyjnej podczas tej inicjalizacji.
- Aktywne zadanie jest zapisane w osobnym commicie. Drzewo pozostaje brudne, dlatego Unit 1 stage'uje wyłącznie własne pliki i pojedynczy hunk hygiene w `scripts/check_fieldnote.sh`.

## Potwierdzone wzorce i ważne pliki

- `scripts/source_adapters.py`: adaptery tylko odkrywają/normalizują źródła; lifecycle nie należy do adaptera.
- `scripts/provenance_v1.py`, `scripts/source_commit.py`, `scripts/source_lifecycle.py`, `scripts/quality_gate.py`: zachować evidence, provenance i semantykę `partial`.
- `fieldnote-api/run_coordinator.py` i `scripts/p0_runtime.py`: bieżące wzorce locków, lease i atomowych zapisów do zachowania jako characterization coverage.
- `scripts/catalog_registry.py`, `scripts/import_lionelo_strollers.py`, `scripts/import_lionelo_internal_specs.py`: katalog oraz import danych Lionelo.
- `fieldnote-api/app.py` i `fieldnote-frontend/src/app/App.tsx`: istniejące surface API/UI; refaktoryzować tylko wraz z konkretnym przenoszonym ekranem.
- `scripts/check_fieldnote.sh`: kanoniczna offline bramka.

## Decyzje

- Supabase jest docelowym systemem trwałym dla PostgreSQL, Auth i Storage; frontend używa go wyłącznie do sesji, a dane biznesowe przechodzą przez FastAPI.
- Pipeline jest opakowywany i migrowany przyrostowo, nie przepisywany od zera.
- Benchmark jest zawsze dla jednostki `model + konfiguracja`; cena jest odrębna od rankingu użytkowego; brak danych obniża kompletność, a nie daje zera.
- MVP obejmuje wyłącznie polski rynek wózków, 34 produkty Lionelo i obecnych realnych konkurentów.

## Designerski kontekst

- Źródło prawdy: `docs/UX_REDESIGN.md` (istnieje).
- Figma: brak (`figma_spec: null`, `figma_screens: {}`).
- Nie wykonywać pełnego redesignu; utrzymać istniejące URL-e i język wizualny przy migracji ekranów.

## Wyniki wykonania i testów

- Unit 1 dodał przykładowe pliki środowiskowe, repo hygiene test, CI, Dependabot i security baseline. Pliki lokalnych env, wejść, outputów, runów i artefaktów są ignorowane; istniejące lokalne pliki nie zostały usunięte.
- `python3 -m unittest tests/test_repository_hygiene.py`: PASS (2 testy).
- `bash scripts/check_fieldnote.sh`: PASS. Backend unit/integration/fixture tests, checkery P0/P1, dry-run provenance i frontend typecheck/test/build przeszły bez Firecrawl/OpenAI.
- Build Vite zgłosił nieblokujące ostrzeżenie o chunku większym niż 500 kB; nie jest to część Unit 1.

## Blokery i ryzyka

- Brudne drzewo robocze: konieczne ścisłe, jawne stage'owanie plików bieżącego unitu.
- Istniejące lokalne dane, outputy i środowiska nie mogą trafić do repo; Unit 1 ma utworzyć audytowalny baseline.
- Live provider calls i koszty są poza automatyczną weryfikacją.

## Przekazanie

- **Bieżący unit:** Unit 1 — Utworzyć bezpieczny baseline repozytorium i CI
- **Status:** completed; oczekuje na `dev-docs-review`
- **Pliki w toku:** `.gitignore`, trzy `.env.example`, `.github/`, `docs/SECURITY_BASELINE.md`, `scripts/check_fieldnote.sh`, `tests/test_repository_hygiene.py`, `docs/active/fieldnote-stroller-mvp/`
- **Ostatnie testy:** hygiene test PASS; `scripts/check_fieldnote.sh` PASS
- **Bloker:** brak
- **Następny krok:** `$dev-docs-review docs/active/fieldnote-stroller-mvp 1`
