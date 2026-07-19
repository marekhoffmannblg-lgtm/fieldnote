# FIELDNOTE Repair Plan

Plan jest ewolucyjny: zachowuje istniejące snapshoty, source registry, model states i skrypty. Nie zakłada przepisywania aplikacji od zera. Kolejność jest wiążąca, ponieważ pierwsze zadania zabezpieczają dane przed kolejnymi migracjami.

## P0 — blokery i ryzyko utraty danych

### 1. Koordynator runu i blokady

- **Problem:** równoległe runy mogą nadpisać kolejki, `new_offers.csv`, model state i globalne raporty.
- **Przyczyna:** brak locka per `group_key`, brak globalnego locka agregatów, shared mutable files.
- **Pliki:** `fieldnote-api/app.py`, `scripts/run_model_research_pipeline.py`, mały nowy moduł `run_coordinator.py`.
- **Zmiana:** immutable run context, lock per produkt, global lock dla benchmark/coverage, idempotency key, lista touched files.
- **Ryzyko:** deadlock przy niepoprawnym zwalnianiu.
- **Test akceptacyjny:** dwa równoległe runy jednego produktu: drugi czeka/409; dwa różne produkty nie nadpisują danych.
- **Złożoność:** L
- **Zależności:** brak.

### 2. Timeout, cancel i recovery runu

- **Problem:** subprocess może wisieć, a restart API pozostawia `running` bez procesu.
- **Przyczyna:** daemon thread, `subprocess.run/Popen.wait` bez timeoutu i trwałego lease.
- **Pliki:** `fieldnote-api/app.py`, `scripts/run_model_research_pipeline.py`.
- **Zmiana:** timeout per stage, sygnał cancel, heartbeat/lease, startup reconciler ustawiający osierocone runy na interrupted/retryable.
- **Ryzyko:** zbyt krótkie timeouty przerwą prawidłowe pobrania.
- **Test akceptacyjny:** wymuszony hang kończy się terminalnym statusem; restart API odzyskuje manifest bez utraty logu.
- **Złożoność:** L
- **Zależności:** 1.

### 3. Atomowy commit bundle wyników

- **Problem:** przerwanie może pozostawić częściowy cleaner bundle, group, state lub CSV.
- **Przyczyna:** bezpośrednie zapisy do docelowych plików.
- **Pliki:** cleaner, `build_model_groups.py`, `extract_model_facts_cascade.py`, benchmark, coverage, fetcher.
- **Zmiana:** zapis do katalogu/pliku tymczasowego, fsync, walidacja schematu, atomic rename; backup poprzedniej wersji state.
- **Ryzyko:** dodatkowe miejsce na dysku.
- **Test akceptacyjny:** kill w każdym etapie nie uszkadza poprzedniego wyniku; brak połówek bundle.
- **Złożoność:** L
- **Zależności:** 1.

### 4. Kanoniczny status produktu

- **Problem:** 14/14 statusów katalogu jest nieaktualnych; latest failed może przesłonić dobry wynik.
- **Przyczyna:** status zapisany/wyliczany w kilku plikach.
- **Pliki:** katalog registry, API, snapshot exporter, frontend.
- **Zmiana:** `result_status`, `active_run_status`, `last_successful_run_id`, `last_failed_run_id`, `refresh_reason`; pochodny status publiczny.
- **Ryzyko:** migracja może zmienić etykiety UI.
- **Test akceptacyjny:** dobry wynik + nowy failed run nadal daje dostępny produkt z ostrzeżeniem; brak wyniku + failed daje `analysis_failed`.
- **Złożoność:** M
- **Zależności:** 1–3.

## P1 — podstawowy workflow

### 5. Quality gate i rewalidacja finalnych stanów

- **Problem:** ORFEO, NEBO i MOOV mają semantycznie błędne lub słabe pola.
- **Przyczyna:** walidatory poprawiano po utworzeniu stanów; brak obowiązkowej rewalidacji przed commit.
- **Pliki:** `extract_model_facts_cascade.py`, walidatory, model states/history.
- **Zmiana:** deterministyczny quality gate, walidacja field/evidence/source, bezsieciowa migracja 5 modeli z wersją historyczną.
- **Ryzyko:** coverage spadnie, ale będzie prawdziwsze.
- **Test akceptacyjny:** `Rama=czarna`, false NEBO conflict i generic one-hand folding nie przechodzą jako high/locked.
- **Złożoność:** L
- **Zależności:** 3–4.

### 6. Naprawa taksonomii benchmarku

- **Problem:** wszystkie modele są w `Spacerówki lekkie`, w tym MOOV.
- **Przyczyna:** domyślna kategoria w `catalog_registry.py`.
- **Pliki:** `data/catalog/categories.json`, `products.json`, catalog registry, benchmark endpoint/UI.
- **Zmiana:** jawna kategoria przy rejestracji, walidowana macierz kategorii, migracja bez zmiany snapshotów.
- **Ryzyko:** część kategorii będzie miała tylko jeden model.
- **Test akceptacyjny:** benchmark porównuje wyłącznie modele zgodnej kategorii; MOOV nie trafia do lekkich spacerówek.
- **Złożoność:** M
- **Zależności:** 4.

### 7. Jeden trwały manifest historii

- **Problem:** historia jest rozbita na trzy katalogi; globalny UI jest mockiem.
- **Przyczyna:** kolejne warstwy zapisywały osobne formaty.
- **Pliki:** API runs, runner research manifests, group history, `App.tsx`.
- **Zmiana:** kanoniczny manifest z referencjami do wersji, adapter odczytu legacy, realny endpoint listy i retry.
- **Ryzyko:** podwójne liczenie starych runów.
- **Test akceptacyjny:** ORFEO/NEBO/TIK pokazują chronologiczną, deduplikowaną historię; retry wywołuje API.
- **Złożoność:** L
- **Zależności:** 1–4.

### 8. Formalny kontrakt source lifecycle

- **Problem:** selected/fetched/registry/attached/used mają różne liczniki i niejasną semantykę.
- **Przyczyna:** brak wspólnego modelu źródła i roli.
- **Pliki:** queue, source registry builder, groups, product sources API/export.
- **Zmiana:** schema `SourceRecord` z lifecycle, role, status, content_family, assignment i wersją.
- **Ryzyko:** migracja 41 rekordów.
- **Test akceptacyjny:** dla każdego produktu suma stanów rozlicza selected; 7 unassigned ma jawny powód.
- **Złożoność:** L
- **Zależności:** 3–4.

### 9. Bramka build/type/test

- **Problem:** produkcyjny build przechodzi z trzema błędami TypeScript; checkery są ad hoc.
- **Przyczyna:** Vite build nie uruchamia `tsc`; brak CI suite.
- **Pliki:** frontend package scripts/tsconfig, Python test config.
- **Zmiana:** `typecheck && build`, pytest dla walidatorów/registry/run state, minimalny fixture E2E.
- **Ryzyko:** początkowo czerwony build.
- **Test akceptacyjny:** jedna komenda uruchamia types, unit i offline integration; zero błędów.
- **Złożoność:** M
- **Zależności:** brak.

## P2 — spójność danych

### 10. Pełne provenance i niezależność potwierdzeń

- **Problem:** 8 excerpt-only evidence bez source_id; kopie treści mogą potwierdzać się nawzajem.
- **Przyczyna:** legacy evidence shapes i content family niewymuszane w merge.
- **Pliki:** cascade, snapshot exporter, contribution API.
- **Zmiana:** normalized evidence item, source chronology, `content_family_id`, authority weighting, brak backfillu bez dowodu.
- **Ryzyko:** część pól utraci pozorne potwierdzenia.
- **Test akceptacyjny:** każde potwierdzenie ma source_id albo jest jawnie `unattributed_legacy`; klony liczą się raz.
- **Złożoność:** L
- **Zależności:** 5, 8.

### 11. Spójność liczb i braków w UI

- **Problem:** nieprzeanalizowane produkty pokazują `Braki: 0`; liczby źródeł mają różne znaczenia.
- **Przyczyna:** fallbacki do zera i brak nazwanych liczników.
- **Pliki:** exporter, API product/source DTO, `App.tsx`.
- **Zmiana:** nullable metrics i jawne `selected/fetched/attached/used`.
- **Ryzyko:** więcej pustych stanów.
- **Test akceptacyjny:** APINO/ESME pokazują `Nie przeanalizowano`, nie zero braków.
- **Złożoność:** S
- **Zależności:** 4, 8.

## P3 — UX

### 12. Usunięcie lub podłączenie atrap

- **Problem:** Uruchomienia, retry, Integracje i profil wyglądają na realne.
- **Przyczyna:** dane demonstracyjne pozostały w produkcyjnym widoku.
- **Pliki:** `App.tsx`, API history/config.
- **Zmiana:** realne endpointy albo jawny badge Demo i wyłączone akcje.
- **Ryzyko:** tymczasowo mniej ekranów.
- **Test akceptacyjny:** żaden przycisk nie symuluje sukcesu timerem; lista runów odpowiada manifestom.
- **Złożoność:** M
- **Zależności:** 7.

### 13. Ujednolicenie stanów i nawigacji

- **Problem:** martwy przycisk sidebara, mylące coverage i brak rozróżnienia ostrzeżeń.
- **Przyczyna:** stan UI i etykiety rosły niezależnie.
- **Pliki:** `App.tsx`, style/components.
- **Zmiana:** wspólne badges/empty/error/loading, usunięcie martwej kontrolki, objaśnienie coverage.
- **Ryzyko:** niewielki visual regression.
- **Test akceptacyjny:** desktop/mobile, wszystkie publiczne statusy i stany puste bez surowych kodów.
- **Złożoność:** M
- **Zależności:** 4, 11–12.

## P4 — refaktoryzacja ewolucyjna

### 14. Wydzielenie warstw API i frontendu

- **Problem:** `app.py` i `App.tsx` mają po ok. 2000 linii.
- **Przyczyna:** endpointy, IO, domena, worker i wszystkie ekrany są monolityczne.
- **Pliki:** backend/frontend.
- **Zmiana:** repositories, services, routers, typed API client, route-level components; bez zmiany formatów w jednym kroku.
- **Ryzyko:** regresje przy zbyt szerokim PR.
- **Test akceptacyjny:** małe migracje z identycznym fixture E2E; żaden moduł domenowy nie uruchamia subprocess przy imporcie.
- **Złożoność:** XL
- **Zależności:** 1–13.

## P5 — rozszerzenia

### 15. Adaptery źródeł i skalowanie

- **Problem:** brak jednolitego kontraktu dla manufacturer/Amazon/marketplace.
- **Przyczyna:** obecna logika jest Allegro-first i plikowa.
- **Pliki:** nowy interfejs adaptera, registry, classifier, API.
- **Zmiana:** `discover/fetch/normalize/classify` adapter, authority, content family, rate limit, pagination, fixture tests; najpierw manufacturer, potem marketplace, Amazon na końcu.
- **Ryzyko:** koszty i różnice regulaminowe/API.
- **Test akceptacyjny:** to samo źródło przez każdy adapter daje zgodny `SourceRecord`; brak zmian w benchmarku bez validated commit.
- **Złożoność:** XL
- **Zależności:** 1–14.

## Kolejność wykonania

1. Koordynator runu i locki.
2. Timeout/cancel/recovery.
3. Atomowe zapisy.
4. Kanoniczny status produktu.
5. Quality gate i rewalidacja 5 wyników.
6. Taksonomia benchmarku.
7. Trwała historia.
8. Source lifecycle contract.
9. Typecheck i automatyczny test suite.
10. Pełne provenance/content families.
11. Spójne liczniki UI.
12. Usunięcie atrap.
13. Ujednolicenie UX.
14. Ewolucyjne wydzielenie modułów.
15. Adaptery nowych źródeł.

## Kryterium gotowości do nowych źródeł

Punkty 1–10 muszą być zamknięte. Szczególnie wymagane są: brak race conditions, atomowy commit, jeden status produktu, poprawna taksonomia, rewalidowane finalne dane i source contract z content-family independence.
